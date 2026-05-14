# AI Agent Orchestrator: Kiro Builder + Codex Reviewer + Claude Planner

This starter project runs a bounded build-review-plan loop:

1. Claude creates the architecture plan from `PROJECT_BRIEF.md`.
2. Kiro CLI acts as the builder and edits the repository.
3. The configured test command runs.
4. Codex CLI reviews the work and extracts next tasks.
5. Claude gives second feedback and acts as the arbiter.
6. The orchestrator sends a targeted `continue` prompt to Kiro until done or `max_rounds` is reached.

The orchestrator is intentionally conservative: it uses a maximum number of rounds and a no-change detector so you do not accidentally burn credits in an infinite loop.

## Requirements

- Python 3.11+
- Git repository for the target project
- `kiro-cli`
- `codex`
- `claude`
- Auth for each tool

Recommended environment variables:

```bash
export KIRO_API_KEY="..."
export CODEX_API_KEY="..."       # optional if Codex CLI is already logged in
export ANTHROPIC_API_KEY="..."   # optional depending on Claude Code auth mode
```

## Install the starter into your project

Copy these files into the root of the repo you want to build:

```text
ai_orchestrator/
prompts/
.kiro/
AGENTS.md
PROJECT_BRIEF.md
agentloop.toml
```

Then edit:

- `PROJECT_BRIEF.md` with your real project explanation.
- `agentloop.toml` with your repo path, test command, and round limit.
- `.kiro/agents/ai-builder.json` if you want a different Kiro model or tool policy.

## Run

From the target repository root:

```bash
python ai_orchestrator/orchestrator.py --config agentloop.toml
```

Dry-run prompt generation without calling external AI CLIs:

```bash
python ai_orchestrator/orchestrator.py --dry-run --skip-preflight
```

Override project and brief file:

```bash
python ai_orchestrator/orchestrator.py \
  --project /path/to/repo \
  --brief /path/to/repo/PROJECT_BRIEF.md \
  --max-rounds 12
```

## Recommended workflow

1. Start with `max_rounds = 2` and a simple `test_command`.
2. Review `.agentloop/runs/<timestamp>/` after each run.
3. When prompts look good, increase to `max_rounds = 6` or `8`.
4. Keep Codex in `read-only` sandbox for review.
5. Let only the builder edit files unless you intentionally enable another patching role.

## Logs

Every run creates:

```text
.agentloop/runs/YYYYMMDD_HHMMSS/
  effective_config.json
  preflight.json
  round_00_claude_planner_prompt.md
  round_00_claude_planner.md
  round_01_builder_prompt.md
  round_01_kiro_builder.md
  round_01_tests.md
  round_01_codex_review.md
  round_01_claude_review.md
  round_01_claude_arbiter.md
  summary.json
```

Use these logs to debug stalled agents, bad prompts, or repeated feedback.

## How the continue mechanism works

Kiro headless mode cannot receive mid-session input. Instead, this orchestrator:

- stores state in logs,
- resumes Kiro conversation after the first round when configured,
- sends a new prompt containing Codex + Claude feedback,
- detects no-change rounds,
- sends a stronger `CONTINUE` prompt when the builder stalls.

That gives you continuous progress without depending on fragile terminal keystroke automation.

## Safety notes

- Do not run with full trust on untrusted repositories.
- Keep `trust_tools` narrow.
- Never commit `.env` or auth files.
- Use Git branches before long runs.
- Keep a real test command configured as soon as possible.
