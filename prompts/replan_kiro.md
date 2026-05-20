# Replan Prompt — Alisa AI Assistant

The Builder has completed a round. Review what was built and decide the next steps.

## Your Task
1. Check which tasks from the plan are done
2. Identify blockers or issues
3. Decide: continue current phase or move to next phase?
4. Update the plan with remaining/new tasks

## Phases (from PROJECT_BRIEF.md)
1. Core Voice Loop (STT + LLM + TTS)
2. Telegram Bot
3. Reception Mode
4. Online Features
5. Self-improvement

## Output Format
```json
{
  "completed_tasks": [1, 2],
  "current_phase": "Phase 1: Core Voice Loop",
  "continue": true,
  "updated_tasks": [
    {"id": 3, "module": "...", "description": "...", "acceptance": "..."}
  ],
  "feedback": "specific feedback for the builder"
}
```
