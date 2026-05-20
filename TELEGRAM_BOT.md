# Alisa Telegram Bot

Phase 2 implementation of the Alisa AI Assistant - Telegram Bot integration.

## Features

- **Text-based conversations** - Send messages to Alisa via Telegram
- **System status monitoring** - `/status` command shows CPU, RAM, disk usage
- **Command interface** - `/start`, `/help`, `/ask`, `/status`
- **Conversation memory** - Alisa remembers recent conversation context
- **Error handling** - Graceful handling of failures with user-friendly messages

## Setup

1. **Create a Telegram Bot**:
   - Message @BotFather on Telegram
   - Use `/newbot` command
   - Get your bot token

2. **Set Environment Variables**:
   ```bash
   export TELEGRAM_BOT_TOKEN="your_bot_token_here"
   export TELEGRAM_CHAT_ID="your_chat_id"  # Optional - restricts to specific chat
   ```

3. **Install Dependencies**:
   ```bash
   pip install python-telegram-bot psutil
   ```

4. **Run the Bot**:
   ```bash
   python run_telegram_bot.py
   ```

## Commands

- `/start` - Initialize the bot and show welcome message
- `/help` - Show available commands
- `/status` - Display system status (CPU, RAM, disk, temperature)
- `/ask <question>` - Ask a specific question
- Regular messages are processed as questions

## Configuration

The bot uses the same `config.yaml` as the main Alisa system:

```yaml
telegram:
  bot_token: null  # Set via TELEGRAM_BOT_TOKEN env var
  chat_id: null    # Set via TELEGRAM_CHAT_ID env var (optional)
```

## Architecture

- **AlisaBot** - Main bot class handling Telegram integration
- **ConversationMemory** - Maintains conversation context
- **AlisaAssistant** - Core AI processing with memory integration
- **System monitoring** - Uses psutil for hardware stats

## Testing

```bash
pytest tests/test_telegram_bot.py -v
pytest tests/test_memory.py -v
```

## Security

- Bot token is loaded from environment variables (never hardcoded)
- Optional chat ID restriction for private use
- Error messages don't expose system internals
- No file system access through bot commands

## Next Steps (Phase 3)

- Voice message support (STT integration)
- Reception mode notifications
- Guest greeting functionality
- FAQ knowledge base integration
