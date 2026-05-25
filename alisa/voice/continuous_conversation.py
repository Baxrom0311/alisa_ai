"""Continuous conversation — wake word siz davom ettirish.

Google Assistant / Alexa "follow-up mode" kabi:
- Alisa javob bergandan keyin 5 soniya ichida yana gapirsa → wake word kerak emas
- 5 soniya jimlik → yana wake word kutish rejimiga qaytadi
"""

import asyncio
import time

import structlog

logger = structlog.get_logger()

# Default follow-up window
FOLLOW_UP_WINDOW_SEC = 5.0


class ContinuousConversation:
    """Manages follow-up conversation without wake word."""

    def __init__(self, window_sec: float = FOLLOW_UP_WINDOW_SEC):
        self.window_sec = window_sec
        self.last_interaction_time: float = 0
        self.active = False

    def mark_interaction(self):
        """Mark that an interaction just happened (response was given)."""
        self.last_interaction_time = time.time()
        self.active = True

    def is_follow_up_active(self) -> bool:
        """Check if we're still in follow-up window (no wake word needed)."""
        if not self.active:
            return False
        elapsed = time.time() - self.last_interaction_time
        if elapsed < self.window_sec:
            return True
        self.active = False
        return False

    def reset(self):
        """Reset — go back to wake word mode."""
        self.active = False
        self.last_interaction_time = 0


_continuous: ContinuousConversation = None


def get_continuous_conversation() -> ContinuousConversation:
    global _continuous
    if _continuous is None:
        _continuous = ContinuousConversation()
    return _continuous
