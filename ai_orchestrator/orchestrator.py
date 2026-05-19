#!/usr/bin/env python3
"""AI Agent Orchestrator — Kiro Planner + Codex Builder

Three-level nested loop:
  Outer:  Kiro plan cycles            (plan_cycles, default 3)
  Middle: Codex-Kiro review cycles    (review_cycles, default 5)
  Inner:  Codex build iterations      (build_iterations, default 10)

Each level supports early stopping based on AI output:
  - Inner: stops if builder reports complete or no files change
  - Middle: stops if Kiro review verdict is "pass"
  - Outer: stops if Kiro replan marks done

Roles:
  - Kiro (Opus): Planner + Reviewer
  - Codex: Builder / Code writer

Telegram bot notifications keep you informed without watching the terminal.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    tomllib = None  # type: ignore[assignment]

# Handle import regardless of how the script is invoked.
_parent = str(Path(__file__).resolve().parent)
if _parent not in sys.path:
    sys.path.insert(0, _parent)
from telegram_notifier import TelegramNotifier


# ── Data classes ───────────────────────────────────────────────────

@dataclasses.dataclass
class CommandResult:
    name: str
    cmd: List[str]
    returncode: int
    stdout: str
    stderr: str
    seconds: float
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    def combined(self, limit: int = 24000) -> str:
        text = ""
        if self.stdout.strip():
            text += f"STDOUT:\n{self.stdout.strip()}\n"
        if self.stderr.strip():
            text += f"STDERR:\n{self.stderr.strip()}\n"
        if len(text) > limit:
            return text[:limit] + "\n...[truncated by orchestrator]"
        return text


class OrchestratorError(RuntimeError):
    pass


# ── Default configuration ─────────────────────────────────────────

DEFAULT_CONFIG: Dict[str, Any] = {
    "project": {
        "path": ".",
        "brief_file": "PROJECT_BRIEF.md",
        "test_command": "",
        "logs_dir": ".agentloop/runs",
    },
    "loop": {
        "plan_cycles": 3,
        "review_cycles": 5,
        "build_iterations": 10,
        "no_change_limit": 2,
        "sleep_between_rounds_sec": 1,
        "max_total_builds": 50,
        "max_discovery_rounds": 2,
    },
    "kiro": {
        "enabled": True,
        "command": "kiro-cli",
        "agent": "ai-planner",
        "timeout_sec": 3600,
        "resume": False,
        "trust_tools": "",
        "trust_all_tools": True,
        "require_mcp_startup": False,
        "instruction_arg": "Follow the orchestration instructions from STDIN exactly.",
    },
    "codex": {
        "enabled": True,
        "command": "codex",
        "timeout_sec": 3600,
        "sandbox": "workspace-write",
    },
    "telegram": {
        "enabled": False,
        "bot_token": "",
        "chat_id": "",
    },
    "git": {
        "auto_push": False,
        "branch": "main",
        "commit_message": "",
    },
}


# ── Utility functions ──────────────────────────────────────────────

def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = json.loads(json.dumps(base))
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return json.loads(json.dumps(DEFAULT_CONFIG))
    if tomllib is None:
        raise OrchestratorError(
            "Python 3.11+ is required for TOML config, or install tomli."
        )
    with path.open("rb") as f:
        user_cfg = tomllib.load(f)
    return deep_merge(DEFAULT_CONFIG, user_cfg)


def ensure_project_root(project_path: Path) -> Path:
    root = project_path.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise OrchestratorError(f"Project path does not exist: {root}")
    return root


def now_slug() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def read_text(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return default


def render_template(template_path: Path, **kwargs: str) -> str:
    text = read_text(template_path)
    if not text:
        raise OrchestratorError(f"Missing prompt template: {template_path}")
    for key, value in kwargs.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def trim(text: str, limit: int = 20000) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + "\n...[middle truncated by orchestrator]...\n" + text[-half:]


# ── Shell & process helpers ────────────────────────────────────────

def run_command(
    name: str,
    cmd: List[str],
    cwd: Path,
    timeout_sec: int,
    input_text: Optional[str] = None,
    env_extra: Optional[Dict[str, str]] = None,
) -> CommandResult:
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
            env=env,
        )
        return CommandResult(
            name, cmd, proc.returncode, proc.stdout, proc.stderr,
            time.monotonic() - start,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            name, cmd, 124,
            exc.stdout or "",
            (exc.stderr or "") + f"\nTimed out after {timeout_sec}s.",
            time.monotonic() - start,
            timed_out=True,
        )


def run_shell(name: str, command: str, cwd: Path, timeout_sec: int = 120) -> CommandResult:
    return run_command(name, ["bash", "-lc", command], cwd=cwd, timeout_sec=timeout_sec)


def command_exists(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def write_result(path: Path, result: CommandResult) -> None:
    body = "\n".join([
        f"# {result.name}",
        "",
        f"returncode: {result.returncode}",
        f"seconds: {result.seconds:.2f}",
        f"timed_out: {result.timed_out}",
        "",
        "## Command",
        "```text",
        " ".join(result.cmd),
        "```",
        "",
        "## STDOUT",
        "```text",
        result.stdout,
        "```",
        "",
        "## STDERR",
        "```text",
        result.stderr,
        "```",
    ])
    write_text(path, body)


# ── Preflight ──────────────────────────────────────────────────────

def preflight(config: Dict[str, Any], project_root: Path, run_dir: Path) -> None:
    checks: List[Dict[str, Any]] = []
    for section in ("kiro", "codex"):
        cfg = config.get(section, {})
        if not cfg.get("enabled", False):
            checks.append({"component": section, "enabled": False, "ok": True})
            continue
        cmd = str(cfg.get("command", section))
        checks.append({
            "component": section, "enabled": True,
            "command": cmd, "ok": command_exists(cmd),
        })
    if config.get("kiro", {}).get("enabled") and not os.environ.get("KIRO_API_KEY"):
        checks.append({
            "component": "kiro-auth", "ok": False,
            "note": "KIRO_API_KEY is not set.",
        })
    checks.append({
        "component": "git", "ok": (project_root / ".git").exists(),
        "note": "recommended; Codex may require a Git repository",
    })
    write_text(run_dir / "preflight.json", json.dumps(checks, indent=2))
    hard_fail = [
        c for c in checks
        if c.get("component") in {"kiro", "codex"} and not c.get("ok")
    ]
    if hard_fail:
        names = ", ".join(c["component"] for c in hard_fail)
        raise OrchestratorError(
            f"Missing CLI(s): {names}. See {run_dir / 'preflight.json'}"
        )


# ── Repo inspection ───────────────────────────────────────────────

def collect_repo_snapshot(project_root: Path, test_output: str = "") -> str:
    commands = [
        ("pwd", "pwd"),
        ("git_status", "git status --short || true"),
        ("git_diff_stat", "git diff --stat || true"),
        ("git_diff_names", "git diff --name-status || true"),
        ("untracked", "git ls-files --others --exclude-standard | head -120 || true"),
        (
            "recent_files",
            "find . -maxdepth 3 -type f | sed 's#^./##' "
            "| grep -Ev '(^\\.git/|^\\.agentloop/|node_modules/|\\.venv/|__pycache__/)' "
            "| sort | head -200",
        ),
    ]
    chunks = []
    for label, cmd in commands:
        res = run_shell(label, cmd, cwd=project_root, timeout_sec=60)
        chunks.append(
            f"## {label}\n```text\n{trim(res.stdout + res.stderr, 6000)}\n```"
        )
    if test_output:
        chunks.append(
            f"## latest_test_output\n```text\n{trim(test_output, 12000)}\n```"
        )
    return "\n\n".join(chunks)


def worktree_hash(project_root: Path) -> str:
    parts: List[str] = []
    for cmd in [
        "git status --porcelain=v1 || true",
        "git diff --stat || true",
        "git ls-files --others --exclude-standard | head -200 || true",
        "find . -maxdepth 3 -name '*.py' -newer .git/HEAD 2>/dev/null | head -50 || true",
    ]:
        res = run_shell("hash", cmd, cwd=project_root, timeout_sec=60)
        parts.append(res.stdout)
    return hashlib.sha256(
        "\n".join(parts).encode("utf-8", errors="ignore")
    ).hexdigest()


# ── Agent wrappers ─────────────────────────────────────────────────

def run_tests(config: Dict[str, Any], project_root: Path, log_dir: Path) -> Tuple[bool, str]:
    command = str(config["project"].get("test_command", "")).strip()
    if not command:
        return False, "No test_command configured; skipped."
    result = run_shell("tests", command, cwd=project_root, timeout_sec=1800)
    write_result(log_dir / "tests.md", result)
    return result.ok, result.combined(limit=30000)


def kiro_planner(
    config: Dict[str, Any], project_root: Path, prompt: str,
) -> CommandResult:
    """Kiro used as planner/reviewer (read-only, Opus model)."""
    cfg = config["kiro"]
    cmd = [str(cfg.get("command", "kiro-cli")), "chat", "--no-interactive"]
    if cfg.get("agent"):
        cmd.extend(["--agent", str(cfg["agent"])])
    if cfg.get("require_mcp_startup"):
        cmd.append("--require-mcp-startup")
    if cfg.get("trust_all_tools"):
        cmd.append("--trust-all-tools")
    elif cfg.get("trust_tools"):
        cmd.append("--trust-tools=" + str(cfg["trust_tools"]))
    # Pass prompt as the [INPUT] argument
    cmd.append(prompt)
    return run_command(
        "kiro-planner", cmd, cwd=project_root,
        timeout_sec=int(cfg.get("timeout_sec", 3600)),
    )


def codex_builder(config: Dict[str, Any], project_root: Path, prompt: str) -> CommandResult:
    """Codex used as the builder/code writer."""
    cfg = config["codex"]
    cmd = [
        str(cfg.get("command", "codex")),
        "exec", "--sandbox", str(cfg.get("sandbox", "workspace-write")), "-",
    ]
    return run_command(
        "codex-builder", cmd, cwd=project_root,
        timeout_sec=int(cfg.get("timeout_sec", 3600)), input_text=prompt,
    )


# ── JSON extraction ────────────────────────────────────────────────

def extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    stripped = text.strip()
    if not stripped:
        return None
    # Direct parse.
    try:
        value = json.loads(stripped)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    # Fenced code blocks.
    if "```" in text:
        for segment in text.split("```"):
            candidate = segment
            if candidate.lstrip().startswith("json"):
                candidate = candidate.lstrip()[4:]
            try:
                value = json.loads(candidate.strip())
                if isinstance(value, dict):
                    return value
            except json.JSONDecodeError:
                continue
    # Balanced braces scan.
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(text[start : i + 1])
                        if isinstance(value, dict):
                            return value
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return None


# ── History formatting ─────────────────────────────────────────────

def compile_review_history(history: List[Dict[str, Any]]) -> str:
    if not history:
        return "No review history available."
    parts: List[str] = []
    for h in history:
        parts.append(
            f"### Review cycle {h['review_cycle']}\n"
            f"- Builds completed: {h['builds_completed']}\n"
            f"- Tests OK: {h['tests_ok']}\n"
            f"- Builder summary: {h.get('builder_summary', 'N/A')}\n"
            f"- Kiro verdict: {h.get('kiro_verdict', 'N/A')}\n"
            f"- Kiro feedback: {h.get('kiro_feedback', 'N/A')[:500]}\n"
        )
    return "\n".join(parts)


# ── Main orchestrator loop ─────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> int:  # noqa: C901
    parser = argparse.ArgumentParser(
        description="AI Agent Orchestrator — nested build-review-plan loop.",
    )
    parser.add_argument("--config", default="agentloop.toml", help="Path to config TOML.")
    parser.add_argument("--project", default=None, help="Override project.path.")
    parser.add_argument("--brief", default=None, help="Override project.brief_file.")
    parser.add_argument("--plan-cycles", type=int, default=None, help="Override loop.plan_cycles.")
    parser.add_argument("--review-cycles", type=int, default=None, help="Override loop.review_cycles.")
    parser.add_argument("--build-iterations", type=int, default=None, help="Override loop.build_iterations.")
    parser.add_argument("--dry-run", action="store_true", help="Write prompts but skip AI CLI calls.")
    parser.add_argument("--skip-preflight", action="store_true", help="Skip CLI/env checks.")
    args = parser.parse_args(argv)

    # ── Config ──
    cfg_path = Path(args.config).expanduser().resolve()
    config = load_config(cfg_path)
    if args.project:
        config["project"]["path"] = args.project
    if args.brief:
        config["project"]["brief_file"] = args.brief
    if args.plan_cycles is not None:
        config["loop"]["plan_cycles"] = args.plan_cycles
    if args.review_cycles is not None:
        config["loop"]["review_cycles"] = args.review_cycles
    if args.build_iterations is not None:
        config["loop"]["build_iterations"] = args.build_iterations

    project_root = ensure_project_root(Path(config["project"]["path"]))
    logs_base = project_root / str(config["project"].get("logs_dir", ".agentloop/runs"))
    run_dir = logs_base / now_slug()
    run_dir.mkdir(parents=True, exist_ok=True)
    write_text(run_dir / "effective_config.json", json.dumps(config, indent=2))

    if not args.skip_preflight and not args.dry_run:
        preflight(config, project_root, run_dir)

    brief_path = project_root / str(config["project"].get("brief_file", "PROJECT_BRIEF.md"))
    brief = read_text(brief_path)
    if not brief.strip():
        raise OrchestratorError(f"Brief is empty or missing: {brief_path}")

    prompts_dir = Path(__file__).resolve().parents[1] / "prompts"

    # ── Telegram ──
    tg_cfg = config.get("telegram", {})
    tg = TelegramNotifier(
        bot_token=tg_cfg.get("bot_token", "") or os.environ.get("TG_BOT_TOKEN", ""),
        chat_id=tg_cfg.get("chat_id", "") or os.environ.get("TG_CHAT_ID", ""),
        enabled=tg_cfg.get("enabled", False),
    )

    # ── Loop parameters ──
    plan_cycles = int(config["loop"].get("plan_cycles", 3))
    review_cycles = int(config["loop"].get("review_cycles", 5))
    build_iterations = int(config["loop"].get("build_iterations", 10))
    no_change_limit = int(config["loop"].get("no_change_limit", 2))
    sleep_sec = float(config["loop"].get("sleep_between_rounds_sec", 1))
    max_total_builds = int(config["loop"].get("max_total_builds", 50))
    max_discovery_rounds = int(config["loop"].get("max_discovery_rounds", 2))

    kiro_enabled = config["kiro"].get("enabled", True)
    codex_enabled = config["codex"].get("enabled", True)

    print(f"[agentloop] project: {project_root}")
    print(f"[agentloop] logs:    {run_dir}")
    print(f"[agentloop] cycles:  plan={plan_cycles}  review={review_cycles}  build={build_iterations}")
    print(f"[agentloop] roles:   Kiro=planner+reviewer  Codex=builder")

    tg.notify_start(project_root.name, plan_cycles, review_cycles, build_iterations)

    # ── State ──
    kiro_plan = ""
    done = False
    final_reason = "Max plan cycles reached."
    total_builds = 0
    discovery_rounds = 0
    pc = 0  # plan cycle counter (set properly in loop)

    # ═══════════════════════════════════════════════════════════════
    #  OUTER LOOP: Kiro plan cycles
    # ═══════════════════════════════════════════════════════════════
    for pc in range(1, plan_cycles + 1):
        plan_dir = run_dir / f"plan_{pc:02d}"
        plan_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n{'=' * 60}")
        print(f"[agentloop] PLAN CYCLE {pc}/{plan_cycles}")
        print(f"{'=' * 60}")

        # ── Kiro initial plan (cycle 1 only) ──
        if pc == 1:
            if kiro_enabled:
                plan_prompt = render_template(
                    prompts_dir / "planner_kiro.md", brief=brief,
                )
                write_text(plan_dir / "kiro_plan_prompt.md", plan_prompt)
                if args.dry_run:
                    kiro_plan = "DRY RUN: Kiro planner not executed."
                else:
                    result = kiro_planner(config, project_root, plan_prompt)
                    write_result(plan_dir / "kiro_plan_output.md", result)
                    kiro_plan = result.combined(limit=30000)
            else:
                kiro_plan = brief  # Use brief as the plan when Kiro is disabled
            tg.notify_plan(pc, plan_cycles, kiro_plan[:500])

        # For pc > 1: kiro_plan was updated by previous cycle's replan.
        if pc > 1:
            write_text(plan_dir / "kiro_plan_carried.md", kiro_plan)
            tg.notify_plan(pc, plan_cycles, kiro_plan[:500])

        kiro_feedback = ""
        review_history: List[Dict[str, Any]] = []
        last_test_output = ""

        # ═══════════════════════════════════════════════════════════
        #  MIDDLE LOOP: Codex build + Kiro review cycles
        # ═══════════════════════════════════════════════════════════
        for rc in range(1, review_cycles + 1):
            review_dir = plan_dir / f"review_{rc:02d}"
            review_dir.mkdir(parents=True, exist_ok=True)

            print(f"\n  {'-' * 50}")
            print(f"  [agentloop] REVIEW CYCLE {rc}/{review_cycles}")
            print(f"  {'-' * 50}")

            no_change_streak = 0
            builder_output = ""
            builds_completed = 0

            # ═══════════════════════════════════════════════════════
            #  INNER LOOP: Codex build iterations
            # ═══════════════════════════════════════════════════════
            for bi in range(1, build_iterations + 1):
                total_builds += 1
                builds_completed = bi
                print(f"    [agentloop] Build {bi}/{build_iterations}  (total #{total_builds})")

                # Safety: max total builds limit
                if total_builds > max_total_builds:
                    print(f"    [agentloop] Max total builds ({max_total_builds}) reached — stopping")
                    done = True
                    final_reason = f"Max total builds limit ({max_total_builds}) reached."
                    break

                snapshot = collect_repo_snapshot(project_root)

                if bi == 1:
                    # First build: full prompt with plan + feedback
                    build_prompt = render_template(
                        prompts_dir / "builder_codex.md",
                        round_no=str(total_builds),
                        brief=trim(brief, 30000),
                        kiro_plan=trim(kiro_plan, 30000),
                        previous_feedback=trim(kiro_feedback, 30000),
                        previous_builder_output=trim(builder_output, 16000),
                        repo_snapshot=trim(snapshot, 24000),
                        next_prompt_override="",
                    )
                else:
                    # Continue: lighter prompt
                    build_prompt = render_template(
                        prompts_dir / "continue_codex.md",
                        build_iter=str(bi),
                        total_build_iters=str(build_iterations),
                        review_cycle=str(rc),
                        brief=trim(brief, 12000),
                        kiro_plan=trim(kiro_plan, 12000),
                        previous_feedback=trim(kiro_feedback, 8000),
                        repo_snapshot=trim(snapshot, 12000),
                    )

                write_text(review_dir / f"build_{bi:02d}_prompt.md", build_prompt)

                if args.dry_run or not codex_enabled:
                    builder_output = "DRY RUN or Codex disabled: builder not executed."
                else:
                    hash_before = worktree_hash(project_root)
                    result = codex_builder(config, project_root, build_prompt)
                    write_result(review_dir / f"build_{bi:02d}_output.md", result)
                    builder_output = result.combined(limit=40000)

                    if not result.ok:
                        builder_output += (
                            "\n\n[orchestrator] Codex returned non-zero exit code."
                        )

                    # No-change detection
                    hash_after = worktree_hash(project_root)
                    report = extract_json_object(result.stdout or "")
                    builder_reports_changes = (
                        report and report.get("files_changed")
                        and len(report["files_changed"]) > 0
                    )
                    if hash_before == hash_after and not builder_reports_changes:
                        no_change_streak += 1
                        print(f"    [agentloop] No change (streak: {no_change_streak})")
                    else:
                        no_change_streak = 0
                        if builder_reports_changes:
                            print(f"    [agentloop] Builder changed: {report['files_changed'][:3]}")

                    if no_change_streak >= no_change_limit:
                        print("    [agentloop] No-change limit hit — ending build phase")
                        break

                    # Builder self-report: complete
                    if report and report.get("state") == "complete":
                        print("    [agentloop] Builder reports complete")
                        break

                if bi < build_iterations:
                    time.sleep(sleep_sec)

            # ── End of build iterations ──
            tg.notify_build_done(pc, rc, builds_completed)

            # ── Run tests ──
            tests_ok, test_output = run_tests(config, project_root, review_dir)
            last_test_output = test_output

            # ── Kiro review ──
            kiro_verdict = "unknown"
            if kiro_enabled:
                snapshot_after = collect_repo_snapshot(project_root, test_output)
                review_prompt = render_template(
                    prompts_dir / "review_kiro.md",
                    round_no=str(rc),
                    brief=trim(brief, 30000),
                    builder_output=trim(builder_output, 24000),
                    repo_snapshot=trim(snapshot_after, 30000),
                    test_output=trim(test_output, 20000),
                )
                write_text(review_dir / "kiro_review_prompt.md", review_prompt)

                if args.dry_run:
                    kiro_feedback = "DRY RUN: Kiro reviewer not executed."
                else:
                    result = kiro_planner(config, project_root, review_prompt)
                    write_result(review_dir / "kiro_review_output.md", result)
                    kiro_feedback = result.combined(limit=40000)

                    verdict_json = extract_json_object(result.stdout or "")
                    if verdict_json:
                        kiro_verdict = str(verdict_json.get("verdict", "unknown"))
                        # Extract direct builder instruction
                        bp = verdict_json.get("builder_prompt", "")
                        if bp:
                            kiro_feedback = f"DIRECT INSTRUCTION: {bp}\n\nFull review:\n{kiro_feedback}"

                tg.notify_review(pc, rc, review_cycles, kiro_feedback[:300])
            else:
                kiro_feedback = "Kiro reviewer disabled."

            review_history.append({
                "review_cycle": rc,
                "builds_completed": builds_completed,
                "tests_ok": tests_ok,
                "builder_summary": builder_output[:500],
                "kiro_verdict": kiro_verdict,
                "kiro_feedback": kiro_feedback[:800],
            })

            # Early stop: Kiro says pass
            if kiro_verdict == "pass":
                print("  [agentloop] Kiro verdict: pass — ending review cycles")
                break

            if rc < review_cycles:
                time.sleep(sleep_sec)

        # ── End of review cycles ──

        # ═══════════════════════════════════════════════════════════
        #  Kiro replan (end of each plan cycle)
        # ═══════════════════════════════════════════════════════════
        if kiro_enabled:
            history_text = compile_review_history(review_history)
            snapshot = collect_repo_snapshot(project_root, last_test_output)
            replan_prompt = render_template(
                prompts_dir / "replan_kiro.md",
                plan_cycle=str(pc),
                total_plan_cycles=str(plan_cycles),
                brief=trim(brief, 30000),
                kiro_plan=trim(kiro_plan, 20000),
                history=trim(history_text, 30000),
                test_output=trim(last_test_output, 12000),
                repo_snapshot=trim(snapshot, 24000),
            )
            write_text(plan_dir / "kiro_replan_prompt.md", replan_prompt)

            if args.dry_run:
                replan_text = json.dumps({
                    "done": False, "reason": "dry run",
                    "updated_plan": "Continue implementation.",
                    "next_review_cycles": review_cycles,
                    "next_build_iterations": build_iterations,
                })
            else:
                replan_result = kiro_planner(config, project_root, replan_prompt)
                write_result(plan_dir / "kiro_replan_output.md", replan_result)
                replan_text = replan_result.stdout or replan_result.stderr

            replan_json = extract_json_object(replan_text)
            write_text(
                plan_dir / "kiro_replan_parsed.json",
                json.dumps(replan_json or {}, indent=2),
            )

            if replan_json:
                done = bool(replan_json.get("done", False))
                final_reason = str(
                    replan_json.get("reason", f"Plan cycle {pc} complete.")
                )
                # Dynamic cycles: Kiro decides next cycle parameters
                if replan_json.get("next_review_cycles"):
                    review_cycles = min(int(replan_json["next_review_cycles"]), 10)
                    print(f"  [agentloop] Dynamic: next review_cycles={review_cycles}")
                if replan_json.get("next_build_iterations"):
                    build_iterations = min(int(replan_json["next_build_iterations"]), 20)
                    print(f"  [agentloop] Dynamic: next build_iterations={build_iterations}")

                if not done:
                    updated = str(replan_json.get("updated_plan", "")).strip()
                    if updated:
                        kiro_plan = updated
                    else:
                        kiro_plan = replan_text

            tg.notify_replan(
                pc, plan_cycles,
                (final_reason if done else kiro_plan)[:500],
            )

        # ═══════════════════════════════════════════════════════════
        #  Auto-discovery: when done, analyze for new opportunities
        # ═══════════════════════════════════════════════════════════
        if done and kiro_enabled and not args.dry_run:
            discovery_rounds += 1
            if discovery_rounds > max_discovery_rounds:
                print(f"  [agentloop] Max discovery rounds ({max_discovery_rounds}) reached — stopping")
            else:
                print(f"  [agentloop] Running auto-discovery analysis ({discovery_rounds}/{max_discovery_rounds})...")
                snapshot = collect_repo_snapshot(project_root, last_test_output)
                discovery_prompt = render_template(
                    prompts_dir / "discovery_kiro.md",
                    brief=trim(brief, 30000),
                    repo_snapshot=trim(snapshot, 24000),
                    test_output=trim(last_test_output, 12000),
                )
                write_text(plan_dir / "kiro_discovery_prompt.md", discovery_prompt)
                discovery_result = kiro_planner(config, project_root, discovery_prompt)
                write_result(plan_dir / "kiro_discovery_output.md", discovery_result)

                discovery_json = extract_json_object(discovery_result.stdout or "")
                if discovery_json and discovery_json.get("new_tasks"):
                    new_tasks = discovery_json["new_tasks"]
                    print(f"  [agentloop] Discovery found {len(new_tasks)} new tasks")
                    tg.send(
                        f"🔎 *Auto-discovery* ({discovery_rounds}/{max_discovery_rounds})\n\n"
                        f"Found {len(new_tasks)} improvement opportunities:\n"
                        + "\n".join(f"• {t}" for t in new_tasks[:5])
                    )
                    if discovery_json.get("should_continue", False):
                        done = False
                        kiro_plan = str(discovery_json.get("updated_plan", ""))
                        final_reason = "Auto-discovery found new tasks."
                        review_cycles = min(int(discovery_json.get("next_review_cycles", 3)), 10)
                        build_iterations = min(int(discovery_json.get("next_build_iterations", 5)), 20)
                        print(f"  [agentloop] Continuing with discovery plan (R={review_cycles}, B={build_iterations})")
                else:
                    print(f"  [agentloop] No new tasks discovered — truly done.")

        if done:
            print(f"\n[agentloop] DONE: {final_reason}")
            break

        if pc < plan_cycles:
            time.sleep(sleep_sec)

    # ═══════════════════════════════════════════════════════════════
    #  Summary
    # ═══════════════════════════════════════════════════════════════
    summary = {
        "done": done,
        "reason": final_reason,
        "plan_cycles_completed": pc,
        "total_build_iterations": total_builds,
        "logs": str(run_dir),
    }
    write_text(run_dir / "summary.json", json.dumps(summary, indent=2))
    tg.notify_done(summary)
    print(json.dumps(summary, indent=2))

    # ═══════════════════════════════════════════════════════════════
    #  Git push when production-ready
    # ═══════════════════════════════════════════════════════════════
    git_cfg = config.get("git", {})
    if done and git_cfg.get("auto_push", False) and not args.dry_run:
        branch = str(git_cfg.get("branch", "main"))
        commit_msg = str(git_cfg.get("commit_message", f"[agentloop] Production-ready: {final_reason[:80]}"))
        print(f"\n[agentloop] Pushing to GitHub ({branch})...")
        tg.send(f"📦 *Pushing to GitHub* branch: `{branch}`")

        # git add all changes
        res = run_shell("git-add", "git add -A", cwd=project_root, timeout_sec=60)
        if not res.ok:
            print(f"[agentloop] git add failed: {res.stderr}")
        else:
            # git commit
            res = run_shell(
                "git-commit",
                f'git commit -m "{commit_msg}"',
                cwd=project_root, timeout_sec=60,
            )
            if not res.ok and "nothing to commit" not in res.stdout + res.stderr:
                print(f"[agentloop] git commit failed: {res.stderr}")
            else:
                # git push
                res = run_shell(
                    "git-push",
                    f"git push -u origin {branch}",
                    cwd=project_root, timeout_sec=120,
                )
                if res.ok:
                    print(f"[agentloop] ✅ Pushed to origin/{branch}")
                    tg.send(f"✅ *Pushed to GitHub* origin/{branch}")
                else:
                    print(f"[agentloop] git push failed: {res.stderr}")
                    tg.send(f"❌ *Push failed*: {res.stderr[:200]}")

    return 0 if done else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OrchestratorError as exc:
        print(f"[agentloop:error] {exc}", file=sys.stderr)
        raise SystemExit(1)
