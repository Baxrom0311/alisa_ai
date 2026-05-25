"""Proactive mode — Alisa o'zi gapiradi (Alexa+ kabi).

Amazon Alexa+ (2025): Reactive → Proactive shift
- Ertalab salomlash + ob-havo
- Eslatmalar (uchrashuv, dori, mashg'ulot)
- Muhim yangiliklar
- Tun vaqtida jim bo'lish

Google Assistant: Proactive notifications, routines
Apple Siri: Suggestions based on time/location
"""

import asyncio
from datetime import datetime, time
from typing import List, Callable, Optional

import structlog

from alisa.core.config import get_config

logger = structlog.get_logger()


class ProactiveManager:
    """Manages proactive notifications and routines."""

    def __init__(self, speak_callback: Optional[Callable] = None):
        self.speak = speak_callback  # async function to speak text
        self.reminders: List[dict] = []
        self.routines: List[dict] = self._default_routines()
        self._running = False
        self._last_greeting = None

    def _default_routines(self) -> List[dict]:
        """Default daily routines (Alexa+ style)."""
        return [
            {
                "name": "morning_greeting",
                "time": time(7, 0),
                "message_fn": self._morning_message,
                "days": [0, 1, 2, 3, 4, 5, 6],  # Har kuni
            },
            {
                "name": "evening_summary",
                "time": time(21, 0),
                "message_fn": self._evening_message,
                "days": [0, 1, 2, 3, 4, 5, 6],
            },
        ]

    async def start(self):
        """Start proactive monitoring loop."""
        self._running = True
        logger.info("proactive_mode_started")
        while self._running:
            await self._check_routines()
            await self._check_reminders()
            await asyncio.sleep(30)  # Check every 30 seconds

    def stop(self):
        self._running = False

    def add_reminder(self, message: str, remind_at: datetime):
        """Add a reminder."""
        self.reminders.append({"message": message, "time": remind_at, "fired": False})
        logger.info("reminder_added", message=message[:50], time=remind_at.isoformat())

    async def _check_routines(self):
        """Check if any routine should fire."""
        now = datetime.now()
        current_time = now.time()
        current_day = now.weekday()

        for routine in self.routines:
            if current_day not in routine["days"]:
                continue

            routine_time = routine["time"]
            # Check if within 1 minute window
            if (routine_time.hour == current_time.hour and
                routine_time.minute == current_time.minute):

                # Avoid firing twice
                key = f"{routine['name']}_{now.date()}"
                if key == self._last_greeting:
                    continue
                self._last_greeting = key

                message = routine["message_fn"]()
                if message and self.speak:
                    await self.speak(message)

    async def _check_reminders(self):
        """Check and fire due reminders."""
        now = datetime.now()
        for reminder in self.reminders:
            if reminder["fired"]:
                continue
            if now >= reminder["time"]:
                reminder["fired"] = True
                if self.speak:
                    await self.speak(f"Eslatma: {reminder['message']}")

        # Clean old reminders
        self.reminders = [r for r in self.reminders if not r["fired"]]

    def _morning_message(self) -> str:
        """Generate morning greeting."""
        now = datetime.now()
        weekday_uz = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba",
                      "Juma", "Shanba", "Yakshanba"][now.weekday()]
        return f"Xayrli tong! Bugun {weekday_uz}, {now.day}-{now.strftime('%B')}. Yaxshi kun tilayman!"

    def _evening_message(self) -> str:
        """Generate evening summary."""
        return "Xayrli kech! Bugungi kun yaxshi o'tdi degan umiddaman. Yaxshi dam oling!"
