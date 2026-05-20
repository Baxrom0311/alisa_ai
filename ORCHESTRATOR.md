# Main Orchestrator Usage

The main orchestrator (`main.py`) provides a unified entry point for running all Alisa modes.

## Usage

```bash
# Run all modes (default)
./main.py

# Run specific mode
./main.py --mode voice      # Voice assistant only
./main.py --mode telegram   # Telegram bot only  
./main.py --mode reception  # Reception mode only

# Set log level
./main.py --log-level DEBUG
```

## Environment Variables

- `TELEGRAM_BOT_TOKEN` - Required for Telegram functionality
- `TELEGRAM_CHAT_ID` - Optional, for notifications

## Modes

1. **Voice Mode**: Wake word detection → STT → LLM → TTS
2. **Telegram Mode**: Bot for remote control and text interaction
3. **Reception Mode**: Guest greeting with Telegram notifications

When running all modes together, they work in coordination:
- Reception mode sends notifications via Telegram
- All modes share the same AI assistant for consistent responses
- Graceful shutdown handles all components properly

## Integration

The orchestrator handles:
- Starting/stopping all components
- Inter-component communication (notifications)
- Error handling and recovery
- Graceful shutdown on SIGINT
