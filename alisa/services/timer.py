"""Timer va Budilnik moduli.

"5 daqiqadan keyin eslatib qo'y" → Timer
"Ertalab 7 da uyg'ot" → Budilnik
"Taymerlarni ko'rsat" → Ro'yxat
"Taymerni o'chir" → Bekor qilish
"""

import asyncio
import re
from datetime import datetime, timedelta
from typing import Optional, Callable, List, Dict

import structlog

logger = structlog.get_logger()


class TimerManager:
    """Manages timers and alarms."""

    def __init__(self, on_fire: Optional[Callable] = None):
        self.on_fire = on_fire  # async callback(message)
        self.timers: List[Dict] = []
        self._tasks: List[asyncio.Task] = []

    def parse_and_create(self, text: str) -> Optional[str]:
        """Parse timer/alarm command from text. Returns confirmation or None."""
        text_lower = text.lower()

        # Timer: "5 daqiqa", "30 sekund", "2 soat"
        m = re.search(r"(\d+)\s*(daqiqa|minut|sekund|sekunt|soat|час|минут|секунд|minute|second|hour)", text_lower)
        if m:
            amount = int(m.group(1))
            unit = m.group(2)
            seconds = self._to_seconds(amount, unit)
            if seconds > 0:
                label = re.sub(r".*?(taymer|timer|eslatib|напомни|remind).*?", "", text_lower).strip() or "Timer"
                self._start_timer(seconds, label)
                return f"Timer {amount} {unit} ga qo'yildi."

        # Alarm: "7:00 da", "soat 7 da"
        m = re.search(r"(\d{1,2})[:\s](\d{2})", text_lower)
        if m:
            hour, minute = int(m.group(1)), int(m.group(2))
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                self._start_alarm(hour, minute)
                return f"Budilnik soat {hour}:{minute:02d} ga qo'yildi."

        return None

    def get_active(self) -> List[str]:
        """Get list of active timers."""
        now = datetime.now()
        active = []
        for t in self.timers:
            if not t["fired"]:
                remaining = (t["fire_at"] - now).total_seconds()
                if remaining > 0:
                    mins = int(remaining // 60)
                    secs = int(remaining % 60)
                    active.append(f"{t['label']}: {mins}m {secs}s qoldi")
        return active

    def cancel_all(self) -> str:
        """Cancel all timers."""
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        self.timers.clear()
        return "Barcha taymerlar bekor qilindi."

    def _to_seconds(self, amount: int, unit: str) -> int:
        if unit in ("sekund", "секунд", "second", "sekunt"):
            return amount
        if unit in ("daqiqa", "minut", "минут", "minute"):
            return amount * 60
        if unit in ("soat", "час", "hour"):
            return amount * 3600
        return 0

    def _start_timer(self, seconds: int, label: str):
        fire_at = datetime.now() + timedelta(seconds=seconds)
        timer = {"label": label, "fire_at": fire_at, "fired": False}
        self.timers.append(timer)
        task = asyncio.ensure_future(self._wait_and_fire(timer, seconds))
        self._tasks.append(task)

    def _start_alarm(self, hour: int, minute: int):
        now = datetime.now()
        fire_at = now.replace(hour=hour, minute=minute, second=0)
        if fire_at <= now:
            fire_at += timedelta(days=1)
        seconds = (fire_at - now).total_seconds()
        timer = {"label": f"Budilnik {hour}:{minute:02d}", "fire_at": fire_at, "fired": False}
        self.timers.append(timer)
        task = asyncio.ensure_future(self._wait_and_fire(timer, seconds))
        self._tasks.append(task)

    async def _wait_and_fire(self, timer: dict, seconds: float):
        await asyncio.sleep(seconds)
        timer["fired"] = True
        msg = f"⏰ {timer['label']} — vaqt bo'ldi!"
        logger.info("timer_fired", label=timer["label"])
        if self.on_fire:
            await self.on_fire(msg)


_timer_manager: Optional[TimerManager] = None


def get_timer_manager(on_fire=None) -> TimerManager:
    global _timer_manager
    if _timer_manager is None:
        _timer_manager = TimerManager(on_fire=on_fire)
    return _timer_manager
