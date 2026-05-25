"""Multi-language support — O'zbek, Rus, Ingliz tillarini aniqlash va qo'llab-quvvatlash.

Foydalanuvchi qaysi tilda gapirsa, shu tilda javob beradi.
STT avtomatik tilni aniqlaydi, LLM va TTS shu tilga moslashadi.
"""

import re
from typing import Optional, Tuple

import structlog

logger = structlog.get_logger()

# Supported languages
LANGUAGES = {
    "uz": {"name": "O'zbek", "tts_voice": "uz", "greeting": "Sizga qanday yordam bera olaman?"},
    "ru": {"name": "Русский", "tts_voice": "ru", "greeting": "Чем могу помочь?"},
    "en": {"name": "English", "tts_voice": "en", "greeting": "How can I help you?"},
}

# Language detection patterns
_UZ_PATTERNS = re.compile(
    r"(o'z|g'|sh[^\w]|qan|uchun|kerak|bo'l|yo'q|bilan|haqida|nima|qaysi|qanday|salom|rahmat|"
    r"iltimos|yaxshi|bilaman|aytib|menga|sizga|endi|hozir|bugun|kecha)"
)
_RU_PATTERNS = re.compile(
    r"(что|как|где|когда|почему|можно|нужно|пожалуйста|спасибо|привет|здравствуй|"
    r"помоги|скажи|расскажи|сколько|какой|этот|будет|хорошо|давай|ладно)"
)
_EN_PATTERNS = re.compile(
    r"\b(what|how|where|when|why|please|thank|hello|help|tell|can|will|"
    r"would|should|could|the|this|that|with|about|from)\b"
)

# System prompts per language
SYSTEM_PROMPTS = {
    "uz": (
        "Sen Alisa — aqlli yordamchi. Sen faqat o'zbek tilida gaplashasan. "
        "Javoblaring qisqa, aniq va foydali bo'lsin."
    ),
    "ru": (
        "Ты Алиса — умный помощник. Отвечай на русском языке. "
        "Ответы должны быть краткими, точными и полезными."
    ),
    "en": (
        "You are Alisa — a smart assistant. Respond in English. "
        "Keep answers short, clear and helpful."
    ),
}


def detect_language(text: str) -> str:
    """Detect language from text. Returns 'uz', 'ru', or 'en'."""
    if not text:
        return "uz"

    text_lower = text.lower()

    # Check for Cyrillic (Russian)
    cyrillic_count = len(re.findall(r"[а-яёА-ЯЁ]", text))
    # Check for Uzbek-specific Latin chars
    uz_latin = len(re.findall(r"[oO]'|[gG]'|sh|ch", text))

    # If mostly Cyrillic → check if Russian or Uzbek Cyrillic
    if cyrillic_count > len(text) * 0.3:
        # Uzbek Cyrillic has ў, қ, ғ, ҳ
        if re.search(r"[ўқғҳ]", text):
            return "uz"
        if _RU_PATTERNS.search(text_lower):
            return "ru"
        return "ru"  # Default Cyrillic = Russian

    # Latin text
    uz_score = len(_UZ_PATTERNS.findall(text_lower))
    en_score = len(_EN_PATTERNS.findall(text_lower))

    if uz_latin > 0:
        uz_score += uz_latin * 2

    if uz_score > en_score:
        return "uz"
    if en_score > 0:
        return "en"

    return "uz"  # Default


def get_system_prompt(lang: str) -> str:
    """Get system prompt for detected language."""
    return SYSTEM_PROMPTS.get(lang, SYSTEM_PROMPTS["uz"])


def get_tts_config(lang: str) -> dict:
    """Get TTS configuration for language."""
    configs = {
        "uz": {"mms_model": "facebook/mms-tts-uzb-script_latin", "espeak_voice": "uz"},
        "ru": {"mms_model": "facebook/mms-tts-rus", "espeak_voice": "ru"},
        "en": {"mms_model": "facebook/mms-tts-eng", "espeak_voice": "en"},
    }
    return configs.get(lang, configs["uz"])
