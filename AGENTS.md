# Agent Rules — Alisa Project

All AI agents working on this repository must follow these rules:

1. Do not expose secrets, tokens, credentials, or private files.
2. Prefer small, reviewable changes — one module at a time.
3. Run `python -m pytest tests/ -q` after meaningful edits.
4. All code must run on Raspberry Pi 4 (ARM64, 4GB RAM).
5. Core features must work OFFLINE (no internet dependency).
6. Use subprocess for external tools (whisper.cpp, piper, ollama).
7. Keep memory usage minimal — use streaming and generators.
8. Config from config.yaml, never hardcode paths or secrets.
9. Handle errors gracefully — Alisa must never crash.
10. Every module needs a test file in tests/.
