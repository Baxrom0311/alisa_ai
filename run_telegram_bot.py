#!/usr/bin/env python3
"""Run Alisa Telegram Bot."""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from alisa.telegram.bot import AlisaBot

def main():
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Check for required environment variables
    if not os.environ.get('TELEGRAM_BOT_TOKEN'):
        print("Error: TELEGRAM_BOT_TOKEN environment variable is required")
        print("Set it with: export TELEGRAM_BOT_TOKEN='your_bot_token'")
        sys.exit(1)
    
    if not os.environ.get('TELEGRAM_CHAT_ID'):
        print("Warning: TELEGRAM_CHAT_ID not set. Bot will respond to all chats.")
    
    try:
        bot = AlisaBot()
        asyncio.run(bot.start_bot())
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
