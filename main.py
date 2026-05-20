#!/usr/bin/env python3
"""Main entry point for Alisa AI Assistant - unified mode runner."""

import asyncio
import argparse
import logging
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Configure warning filters early
from alisa.core.warnings_filter import setup_warning_filters
setup_warning_filters()

from alisa.core.assistant import AlisaAssistant
from alisa.core.validator import validate_system, get_system_info
from alisa.telegram.bot import AlisaBot
from alisa.reception.greeter import ReceptionGreeter
from alisa.services.scheduler import get_scheduler, schedule_daily_news, schedule_health_check
from alisa.services.web_dashboard import get_web_dashboard

logger = logging.getLogger(__name__)


class AlisaOrchestrator:
    """Main orchestrator for all Alisa modes."""
    
    def __init__(self):
        # Single instances shared across all modes
        self.assistant = AlisaAssistant()
        self.reception_greeter = None
        self.telegram_bot = None
        self.scheduler = get_scheduler()
        self.web_dashboard = None
        self.web_runner = None
        self.running_tasks = []
    
    async def start_voice_mode(self):
        """Start voice assistant mode."""
        logger.info("Starting voice assistant mode...")
        task = asyncio.create_task(self.assistant.start())
        self.running_tasks.append(task)
        return task
    
    async def start_telegram_mode(self):
        """Start Telegram bot mode."""
        logger.info("Starting Telegram bot mode...")
        
        if not os.environ.get('TELEGRAM_BOT_TOKEN'):
            logger.error("TELEGRAM_BOT_TOKEN not set, skipping Telegram mode")
            return None
        
        # Create telegram notifier function
        async def telegram_notifier(message):
            if self.telegram_bot:
                try:
                    await self.telegram_bot.send_notification(message)
                except Exception as e:
                    logger.error(f"Failed to send notification: {e}")
        
        # Create reception greeter if not exists
        if not self.reception_greeter:
            self.reception_greeter = ReceptionGreeter(telegram_notifier=telegram_notifier)
        
        # Pass shared instances to bot
        self.telegram_bot = AlisaBot(assistant=self.assistant, greeter=self.reception_greeter)
        task = asyncio.create_task(self.telegram_bot.start_bot())
        self.running_tasks.append(task)
        return task
    
    async def start_reception_mode(self):
        """Start reception mode."""
        logger.info("Starting reception mode...")
        
        # Create notifier for Telegram integration
        async def telegram_notifier(message):
            if self.telegram_bot:
                try:
                    await self.telegram_bot.send_notification(message)
                except Exception as e:
                    logger.error(f"Failed to send notification: {e}")
        
        # Create reception greeter if not exists
        if not self.reception_greeter:
            self.reception_greeter = ReceptionGreeter(telegram_notifier=telegram_notifier)
        
        task = asyncio.create_task(self.reception_greeter.start_reception_mode())
        self.running_tasks.append(task)
        return task
    
    async def start_web_dashboard(self, port: int = 8080):
        """Start web dashboard for monitoring."""
        logger.info("Starting web dashboard...", port=port)
        
        try:
            self.web_dashboard = get_web_dashboard(port=port)
            self.web_runner = await self.web_dashboard.start()
            logger.info("Web dashboard started", url=f"http://localhost:{port}")
            return True
        except Exception as e:
            logger.error("Failed to start web dashboard", error=str(e))
            return False
    
    async def start_all_modes(self):
        """Start all modes simultaneously."""
        logger.info("Starting all Alisa modes...")
        
        tasks = []
        
        # Start scheduler first
        from alisa.core.config import get_config
        config = get_config()
        if config.get("scheduler", {}).get("enabled", True):
            await self.scheduler.start()
            # Schedule default tasks
            schedule_health_check(30)  # Every 30 minutes
            schedule_daily_news(8, 0)  # Daily at 8:00 AM
        
        # Start web dashboard if enabled
        if config.get("web_dashboard", {}).get("enabled", True):
            port = config.get("web_dashboard", {}).get("port", 8080)
            await self.start_web_dashboard(port=port)
        
        # Start Telegram bot first (for notifications)
        telegram_task = await self.start_telegram_mode()
        if telegram_task:
            tasks.append(telegram_task)
            # Give Telegram bot time to initialize
            await asyncio.sleep(1)
        
        # Start voice assistant
        voice_task = await self.start_voice_mode()
        if voice_task:
            tasks.append(voice_task)
        
        # Start reception mode
        reception_task = await self.start_reception_mode()
        if reception_task:
            tasks.append(reception_task)
        
        if not tasks:
            logger.error("No modes could be started")
            return
        
        try:
            # Wait for all tasks to complete (or until interrupted)
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logger.error(f"Error in orchestrator: {e}")
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Gracefully shutdown all modes."""
        logger.info("Shutting down Alisa...")
        
        # Stop scheduler
        if self.scheduler:
            await self.scheduler.stop()
        
        # Stop web dashboard
        if self.web_runner:
            await self.web_dashboard.stop(self.web_runner)
        
        # Stop all components
        if self.assistant:
            self.assistant.stop()
        
        if self.reception_greeter:
            self.reception_greeter.stop_reception_mode()
        
        if self.telegram_bot:
            await self.telegram_bot.stop_bot()
        
        # Cancel remaining tasks
        for task in self.running_tasks:
            if not task.done():
                task.cancel()
        
        # Wait for tasks to finish cancellation
        if self.running_tasks:
            await asyncio.gather(*self.running_tasks, return_exceptions=True)
        
        logger.info("Alisa shutdown complete")


async def main():
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(description="Alisa AI Assistant")
    parser.add_argument(
        "--mode",
        choices=["voice", "telegram", "reception", "all"],
        default="all",
        help="Mode to run (default: all)"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Log level (default: INFO)"
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip system validation on startup"
    )
    
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run system validation unless skipped
    if not args.skip_validation:
        logger.info("Running system validation...")
        is_valid, issues = validate_system()
        
        if not is_valid:
            logger.error("System validation failed:")
            for issue in issues:
                logger.error(f"  - {issue}")
            logger.warning("Starting anyway... some features may not work properly")
        else:
            logger.info("System validation passed")
        
        # Log system info
        system_info = get_system_info()
        logger.info("System info:", extra=system_info)
    
    orchestrator = AlisaOrchestrator()
    
    try:
        if args.mode == "voice":
            await orchestrator.start_voice_mode()
            await asyncio.gather(*orchestrator.running_tasks)
        elif args.mode == "telegram":
            await orchestrator.start_telegram_mode()
            await asyncio.gather(*orchestrator.running_tasks)
        elif args.mode == "reception":
            await orchestrator.start_reception_mode()
            await asyncio.gather(*orchestrator.running_tasks)
        else:  # all
            await orchestrator.start_all_modes()
    
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        await orchestrator.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
