# Review Prompt — Alisa AI Assistant

You are reviewing code written for Alisa — a Raspberry Pi local AI assistant.

## Review Criteria
1. **Correctness**: Does it do what the task asked?
2. **Pi-compatible**: Will it run on ARM64 with 4GB RAM?
3. **Offline-first**: Does it work without internet?
4. **Error handling**: Will Alisa crash if something fails?
5. **Tests**: Are there meaningful tests?
6. **Security**: No hardcoded secrets, safe subprocess calls

## Output Format
```json
{
  "status": "approve" | "request_changes",
  "issues": [
    {"file": "path", "line": 0, "severity": "high|medium|low", "message": "what's wrong"}
  ],
  "next_tasks": ["what to do next if approved"],
  "done": false
}
```

Set `done: true` only when ALL acceptance criteria from PROJECT_BRIEF.md are met.
