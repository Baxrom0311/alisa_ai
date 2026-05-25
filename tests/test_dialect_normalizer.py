"""Tests for alisa.voice.dialect_normalizer module."""

from alisa.voice.dialect_normalizer import (
    normalize_dialect,
    cyrillic_to_latin,
    post_process_stt,
    get_initial_prompt_for_uzbek,
    _has_cyrillic,
)


class TestCyrillicToLatin:
    def test_basic_conversion(self):
        assert cyrillic_to_latin("салом") == "salom"

    def test_special_chars(self):
        assert cyrillic_to_latin("ўзбек") == "o'zbek"
        assert cyrillic_to_latin("қанақа") == "qanaqa"
        assert cyrillic_to_latin("ғалаба") == "g'alaba"

    def test_mixed_text_unchanged(self):
        assert cyrillic_to_latin("hello") == "hello"

    def test_empty(self):
        assert cyrillic_to_latin("") == ""


class TestHasCyrillic:
    def test_cyrillic_detected(self):
        assert _has_cyrillic("салом") is True
        assert _has_cyrillic("ўзбек") is True

    def test_latin_not_detected(self):
        assert _has_cyrillic("salom") is False
        assert _has_cyrillic("hello world") is False


class TestNormalizeDialect:
    def test_empty_input(self):
        assert normalize_dialect("") == ""
        assert normalize_dialect(None) is None

    def test_cyrillic_conversion(self):
        result = normalize_dialect("Салом")
        assert "salom" in result

    def test_xorazm_dialect(self):
        result = normalize_dialect("қанақа")
        assert result == "qanday"

    def test_whisper_corrections(self):
        result = normalize_dialect("assalomu aleykum")
        assert result == "assalomu alaykum"

    def test_standard_text_unchanged(self):
        result = normalize_dialect("salom")
        assert result == "salom"

    def test_rahmat_variants(self):
        assert "rahmat" in normalize_dialect("рахмат")  # raxmat → rahmat
        assert "rahmat" in normalize_dialect("рахмет")  # raxmet → rahmat


class TestPostProcessSTT:
    def test_empty(self):
        assert post_process_stt("") == ""
        assert post_process_stt(None) == ""

    def test_removes_brackets(self):
        result = post_process_stt("salom [music] dunyo")
        assert "[music]" not in result
        assert "salom" in result

    def test_removes_repeated_words(self):
        result = post_process_stt("salom salom salom dunyo")
        assert result == "salom dunyo"

    def test_full_pipeline(self):
        # Kirill + sheva + whisper artefakt
        result = post_process_stt("Салом [silence] қанақа")
        assert "salom" in result
        assert "qanday" in result
        assert "[silence]" not in result


class TestInitialPrompt:
    def test_returns_uzbek_text(self):
        prompt = get_initial_prompt_for_uzbek()
        assert "Alisa" in prompt
        assert "Assalomu" in prompt
        assert len(prompt) > 50
