# Orchestration steering — Alisa Project

Kiro (Opus) is used as the planner and reviewer in a multi-agent loop.
Codex is used as the builder/code writer.

## Project: Alisa — Raspberry Pi Local AI Assistant
- Voice assistant: whisper.cpp (STT) + Ollama (LLM) + Piper (TTS)
- Telegram bot for remote control
- Reception mode for greeting guests
- Offline-first, online-enhanced

## Planner/Reviewer (Kiro) expectations:
- Create actionable implementation plans following the 5 phases.
- Review builder output for correctness, Pi-compatibility, and offline capability.
- Provide focused, concrete feedback.
- Do not edit files — read-only mode.
- Return structured JSON when requested.

## Builder (Codex) expectations:
- Make concrete edits — one module at a time.
- Use subprocess for whisper.cpp, piper, ollama.
- Run tests after changes.
- Keep RAM usage under 3GB total.
- Return ORCHESTRATOR_REPORT JSON at the end.

## Safety expectations:
- Do not expose Telegram tokens or API keys.
- Do not run destructive commands.
- Keep permissions minimal.
- Prefer reversible edits.
- Never write secrets to code files — use config.yaml or env vars.
