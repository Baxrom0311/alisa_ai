"""Intent detection — tez buyruqlarni LLM siz bajarish.

Amazon Alexa NLU yondashuvi:
- Oddiy buyruqlar (vaqt, timer, ob-havo) → darhol javob (0ms LLM kutish)
- Murakkab savollar → LLM ga yuboriladi

Bu 2-3 soniya tejaydi oddiy buyruqlar uchun!
"""

import re
from datetime import datetime
from typing import Optional, Tuple

import structlog

logger = structlog.get_logger()


# Intent patterns — regex bilan aniqlash (uz + ru + en)
INTENT_PATTERNS = {
    "time": [
        r"soat\s*nech(a|i)", r"hozir\s*soat", r"vaqt",
        r"который\s*час", r"сколько\s*времени", r"время",
        r"what\s*time", r"current\s*time",
    ],
    "date": [
        r"bugun\s*qaysi\s*kun", r"bugun\s*nech(a|i)", r"sana",
        r"какой\s*сегодня\s*день", r"какое\s*число", r"сегодня",
        r"what\s*day", r"today'?s?\s*date",
    ],
    "greeting": [
        r"^salom", r"^assalom", r"^hey\s*alisa", r"^yaxshimisiz",
        r"^привет", r"^здравствуй", r"^добр",
        r"^hello", r"^hi\s", r"^hey\s", r"^good\s*(morning|evening|afternoon)",
    ],
    "thanks": [
        r"rahmat", r"raxmat", r"tashakkur",
        r"спасибо", r"благодар",
        r"thank", r"thanks",
    ],
    "stop": [
        r"^to'xta", r"^bas", r"^yetadi",
        r"^стоп", r"^хватит", r"^замолчи",
        r"^stop", r"^enough", r"^shut\s*up",
    ],
    "volume_up": [
        r"ovoz(ni)?\s*(ko'tar|baland|oshir)",
        r"громче", r"погромче",
        r"louder", r"volume\s*up",
    ],
    "volume_down": [
        r"ovoz(ni)?\s*(pasayt|past|kamayt)",
        r"тише", r"потише",
        r"quieter", r"volume\s*down",
    ],
    "repeat": [
        r"qaytala", r"yana\s*ayt",
        r"повтори", r"ещё\s*раз",
        r"repeat", r"say\s*(it\s*)?again",
    ],
}

# O'zbek kun nomlari
WEEKDAYS_UZ = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]
MONTHS_UZ = ["yanvar", "fevral", "mart", "aprel", "may", "iyun",
             "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"]


def detect_intent(text: str) -> Optional[Tuple[str, str]]:
    """Detect intent from text. Returns (intent, response) or None.
    
    If intent is detected, response is returned immediately without LLM.
    If None, text should be sent to LLM.
    """
    if not text:
        return None

    text_lower = text.lower().strip()

    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                response = _handle_intent(intent)
                if response:
                    logger.info("intent_detected", intent=intent, text=text_lower[:50])
                    return (intent, response)

    return None


def _handle_intent(intent: str) -> Optional[str]:
    """Generate response for detected intent (auto-detects language from context)."""
    from alisa.core.language import detect_language
    now = datetime.now()

    if intent == "time":
        hour = now.hour
        minute = now.minute
        return f"Hozir soat {hour}:{minute:02d}"

    elif intent == "date":
        day = now.day
        month = MONTHS_UZ[now.month - 1]
        weekday = WEEKDAYS_UZ[now.weekday()]
        return f"Bugun {weekday}, {day}-{month}"

    elif intent == "greeting":
        hour = now.hour
        if hour < 12:
            return "Xayrli tong! Sizga qanday yordam bera olaman?"
        elif hour < 18:
            return "Xayrli kun! Sizga qanday yordam bera olaman?"
        else:
            return "Xayrli kech! Sizga qanday yordam bera olaman?"

    elif intent == "thanks":
        return "Arzimaydi! Yana yordam kerak bo'lsa, ayting."

    elif intent == "stop":
        return None

    elif intent == "repeat":
        return None

    elif intent == "volume_up":
        return "Ovoz balandligi oshirildi."

    elif intent == "volume_down":
        return "Ovoz balandligi pasaytirildi."

    return None
