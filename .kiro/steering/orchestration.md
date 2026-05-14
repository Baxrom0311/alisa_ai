# Orchestration steering

Kiro is used as the builder in a multi-agent loop.

Builder expectations:
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
