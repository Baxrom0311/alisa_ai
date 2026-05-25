"""O'zbek tili sheva normalizatsiyasi va STT post-processing.

O'zbek tilida asosiy shevalar:
- Toshkent (adabiy til, standart)
- Farg'ona (a→o, qisqa unlilar)
- Xorazm (g'→q, o→a, maxsus intonatsiya)
- Samarqand/Buxoro (tojik ta'siri, i→e)
- Qashqadaryo/Surxondaryo (janubiy, cho'ziq unlilar)

Bu modul STT natijasini normalizatsiya qiladi — shevadagi so'zlarni
adabiy (standart) shaklga keltiradi.
"""

import re
from typing import Dict, List, Tuple

import structlog

logger = structlog.get_logger()

# Sheva → Adabiy so'z almashtirishlari (LOTIN yozuvida, chunki kirill avval convert qilinadi)
DIALECT_WORD_MAP: Dict[str, str] = {
    # Xorazm shevasi
    "bova": "bola",
    "qanaqa": "qanday",
    "man": "men",
    "san": "sen",
    "ishliyman": "ishlayman",
    "boriyman": "borayapman",
    "ketiyman": "ketayapman",
    "nima qiliysan": "nima qilyapsan",
    "yaxshimisan": "yaxshimisiz",
    "yaxshimisiz": "yaxshimisiz",
    "raxmat": "rahmat",
    "raxmet": "rahmat",
    "rahmet": "rahmat",
    # Farg'ona shevasi
    "nimasa": "nimaga",
    "qayerga": "qayerga",
    "borasanmi": "borasizmi",
    "kelasanmi": "kelasizmi",
    "qilsanmi": "qilasizmi",
    "ishlaysanmi": "ishlaysizmi",
    "bilasanmi": "bilasizmi",
    "xo'p": "xo'p",
    "xop": "xo'p",
    # Samarqand/Buxoro
    "chi": "nima",
    "miya": "miya",
    "kiyim": "kiyim",
    "biya": "bu yerga",
    # Umumiy variantlar
    "assalomu": "assalomu",
    "assalom": "assalom",
    "salom": "salom",
    "salomaleykum": "assalomu alaykum",
    "valeykum": "va alaykum",
    "aleykum": "alaykum",
}

# Kirill → Lotin transliteratsiya
CYRILLIC_TO_LATIN: Dict[str, str] = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d",
    "е": "e", "ё": "yo", "ж": "j", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "x", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "sh", "ъ": "'", "ы": "i", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
    "ў": "o'", "қ": "q", "ғ": "g'", "ҳ": "h",
    # Katta harflar
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D",
    "Е": "E", "Ё": "Yo", "Ж": "J", "З": "Z", "И": "I",
    "Й": "Y", "К": "K", "Л": "L", "М": "M", "Н": "N",
    "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T",
    "У": "U", "Ф": "F", "Х": "X", "Ц": "Ts", "Ч": "Ch",
    "Ш": "Sh", "Щ": "Sh", "Ъ": "'", "Ы": "I", "Ь": "",
    "Э": "E", "Ю": "Yu", "Я": "Ya",
    "Ў": "O'", "Қ": "Q", "Ғ": "G'", "Ҳ": "H",
}

# Whisper ko'p uchraydigan xatolar (o'zbek uchun)
WHISPER_CORRECTIONS: Dict[str, str] = {
    # Whisper ko'pincha o'zbek so'zlarini boshqa tilga o'xshatib yozadi
    "алиса": "alisa",
    "алисa": "alisa",
    "aлиса": "alisa",
    "elisa": "alisa",
    "alissa": "alisa",
    "allisa": "alisa",
    # Umumiy xatolar
    "assalomu aleykum": "assalomu alaykum",
    "salom aleykum": "assalomu alaykum",
}

# Sheva fonetik almashtirishlar (regex pattern → replacement)
PHONETIC_NORMALIZATIONS: List[Tuple[str, str]] = [
    # Xorazm: -ийман → -аяпман / -аyman
    (r"(\w+)ийман\b", r"\1ayman"),
    (r"(\w+)ийсан\b", r"\1aysan"),
    (r"(\w+)ийсиз\b", r"\1aysiz"),
    # Farg'ona: -санми → -сизми
    (r"(\w+)санми\b", r"\1sizmi"),
    (r"(\w+)сенми\b", r"\1sizmi"),
    # Umumiy: ў → o', ғ → g', қ → q, ҳ → h (agar kirill aralash kelsa)
]


def cyrillic_to_latin(text: str) -> str:
    """Kirill yozuvdagi o'zbek matnini lotin yozuviga o'tkazish."""
    result = []
    for char in text:
        if char in CYRILLIC_TO_LATIN:
            result.append(CYRILLIC_TO_LATIN[char])
        else:
            result.append(char)
    return "".join(result)


def normalize_dialect(text: str) -> str:
    """Shevadagi so'zlarni adabiy shaklga keltirish."""
    if not text:
        return text

    normalized = text.lower().strip()

    # 1. Kirill → Lotin (agar whisper kirill qaytarsa)
    if _has_cyrillic(normalized):
        normalized = cyrillic_to_latin(normalized)

    # 2. Whisper xatolarini to'g'rilash
    for wrong, correct in WHISPER_CORRECTIONS.items():
        normalized = normalized.replace(wrong, correct)

    # 3. So'z almashtirishlar (sheva → adabiy)
    words = normalized.split()
    corrected_words = []
    for word in words:
        clean_word = word.strip(".,!?;:")
        if clean_word in DIALECT_WORD_MAP:
            corrected_words.append(DIALECT_WORD_MAP[clean_word])
        else:
            corrected_words.append(word)
    normalized = " ".join(corrected_words)

    # 4. Fonetik normalizatsiya (regex)
    for pattern, replacement in PHONETIC_NORMALIZATIONS:
        normalized = re.sub(pattern, replacement, normalized)

    # 5. Ortiqcha bo'shliqlarni tozalash
    normalized = re.sub(r"\s+", " ", normalized).strip()

    if normalized != text.lower().strip():
        logger.debug("dialect_normalized", original=text, normalized=normalized)

    return normalized


def _has_cyrillic(text: str) -> bool:
    """Matnda kirill harflari bormi tekshirish."""
    return bool(re.search(r"[а-яёўқғҳ]", text, re.IGNORECASE))


def get_initial_prompt_for_uzbek() -> str:
    """Whisper uchun o'zbek tili initial prompt.
    
    Bu prompt whisper ga o'zbek so'zlarini to'g'ri tanishga yordam beradi.
    Ko'p ishlatiladigan so'zlar va iboralar kiritilgan.
    """
    return (
        "Assalomu alaykum. Alisa, menga yordam ber. "
        "Bugun ob-havo qanday? Soat nechida? "
        "Rahmat. Xo'p. Ha. Yo'q. Bilmayman. "
        "Qanday yordam bera olaman? Savol bering. "
        "Yaxshimisiz? Nima yangiliklar bor? "
        "Men tushundim. Kuting. Bir daqiqa."
    )


def post_process_stt(text: str) -> str:
    """STT natijasini to'liq post-processing.
    
    1. Kirill → Lotin
    2. Sheva normalizatsiya
    3. Whisper xatolarini to'g'rilash
    4. Keraksiz belgilarni tozalash
    """
    if not text:
        return ""

    # Asosiy normalizatsiya
    result = normalize_dialect(text)

    # Whisper artefaktlarini tozalash
    # (takroriy so'zlar, [music], [silence] kabi)
    result = re.sub(r"\[.*?\]", "", result)
    result = re.sub(r"\(.*?\)", "", result)

    # Takroriy so'zlarni olib tashlash
    words = result.split()
    if len(words) > 2:
        deduped = [words[0]]
        for i in range(1, len(words)):
            if words[i] != words[i - 1]:
                deduped.append(words[i])
        result = " ".join(deduped)

    return result.strip()
