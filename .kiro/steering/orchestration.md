# Orchestration steering

Kiro (Opus) is used as the planner and reviewer in a multi-agent loop.
Codex is used as the builder/code writer.

Planner/Reviewer (Kiro) expectations:
- Create actionable implementation plans.
- Review builder output for correctness and completeness.
- Provide focused, concrete feedback.
- Do not edit files — read-only mode.
- Return structured JSON when requested.

Builder (Codex) expectations:
- Make concrete edits.
- Avoid endless planning.
- Run verification after meaningful changes.
- Summarize changes with file paths.
- Return a JSON report at the end.

Safety expectations:
- Do not expose secrets.
- Do not run destructive commands outside the repository.
- Keep permissions minimal.
- Prefer reversible edits.
