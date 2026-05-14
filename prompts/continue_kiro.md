# Continue Building

You are in build iteration {{build_iter}} of {{total_build_iters}} (review cycle {{review_cycle}}).

Continue implementing the plan. Pick up where you left off.

## Non-negotiable rules

- Do not ask questions. Make reasonable assumptions and continue.
- Make concrete file changes. Do not only plan.
- Run verification when possible.
- Never commit secrets.

## Brief (condensed)

{{brief}}

## Current plan

{{claude_plan}}

## Latest reviewer feedback

{{previous_feedback}}

## Repository snapshot

{{repo_snapshot}}

## What to do now

1. Look at what was already done.
2. Pick the next unfinished task from the plan.
3. Implement it.
4. Run verification.
5. Move to the next task if time allows.

End with ORCHESTRATOR_REPORT JSON:

```json
{
  "state": "in_progress | complete | blocked",
  "summary": "What you changed this iteration",
  "files_changed": ["path/to/file"],
  "verification": "Commands run and result",
  "next_suggested_task": "What to do next"
}
```
