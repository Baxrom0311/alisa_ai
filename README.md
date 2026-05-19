# AI Agent Orchestrator: Kiro Planner + Codex Builder

This starter project runs a bounded build-review-plan loop:

1. Kiro (Opus) creates the architecture plan from `PROJECT_BRIEF.md`.
2. Codex CLI acts as the builder and edits the repository.
3. The configured test command runs.
4. Kiro (Opus) reviews the work and extracts next tasks.
5. Kiro gives replanning feedback and decides whether to continue.
6. The orchestrator sends a targeted `continue` prompt to Codex until done or `max_rounds` is reached.

## Roles

| Agent | Role | Model |
|-------|------|-------|
| Kiro | Planner + Reviewer | claude-opus-4 |
| Codex | Builder / Code writer | codex default |

## Requirements

- Python 3.11+
- Git repository for the target project
- `kiro-cli`
- `codex`
- Auth for each tool

Recommended environment variables:

```bash
export KIRO_API_KEY="..."
export CODEX_API_KEY="..."       # optional if Codex CLI is already logged in
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
- `.kiro/agents/ai-planner.json` if you want a different Kiro model.

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
  --plan-cycles 3
```

## Recommended workflow

1. Start with `plan_cycles = 1` and a simple `test_command`.
2. Review `.agentloop/runs/<timestamp>/` after each run.
3. When prompts look good, increase to `plan_cycles = 3`.
4. Keep Kiro in read-only mode for planning/review.
5. Let only Codex edit files.

## Logs

Every run creates:

```text
.agentloop/runs/YYYYMMDD_HHMMSS/
  effective_config.json
  preflight.json
  plan_01/
    kiro_plan_prompt.md
    kiro_plan_output.md
    review_01/
      build_01_prompt.md
      build_01_output.md
      tests.md
      kiro_review_prompt.md
      kiro_review_output.md
    kiro_replan_prompt.md
    kiro_replan_output.md
  summary.json
```

## Safety notes

- Do not run with full trust on untrusted repositories.
- Keep `trust_tools` narrow for the planner/reviewer.
- Never commit `.env` or auth files.
- Use Git branches before long runs.
- Keep a real test command configured as soon as possible.
