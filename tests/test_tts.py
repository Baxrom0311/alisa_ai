"""Tests for alisa.voice.tts module (MMS-TTS + fallbacks)."""

from unittest.mock import patch, MagicMock
from pathlib import Path

from alisa.core.config import reset_config


def test_synthesize_empty_text():
    """synthesize returns None for empty text."""
    reset_config()
    from alisa.voice.tts import synthesize
    assert synthesize("") is None
    assert synthesize("   ") is None


@patch("alisa.voice.tts._mms_available", False)
@patch("alisa.voice.tts._synthesize_piper", return_value=None)
@patch("alisa.voice.tts.subprocess.run")
def test_synthesize_espeak_fallback(mock_run, mock_piper):
    """Falls back to espeak-ng when MMS and Piper unavailable."""
    reset_config()

    def side_effect(cmd, **kwargs):
        if "espeak-ng" in cmd:
            out_path = cmd[cmd.index("-w") + 1]
            Path(out_path).write_bytes(b"RIFF" + b"\x00" * 200)
            return MagicMock(returncode=0)
        return MagicMock(returncode=1)

    mock_run.side_effect = side_effect

    from alisa.voice.tts import synthesize
    result = synthesize("Salom")

    assert result is not None
    Path(result).unlink(missing_ok=True)


@patch("alisa.voice.tts._mms_available", False)
@patch("alisa.voice.tts._synthesize_piper", return_value=None)
@patch("alisa.voice.tts._synthesize_espeak", return_value=None)
def test_synthesize_all_fail(mock_espeak, mock_piper):
    """Returns None when all engines fail."""
    reset_config()
    from alisa.voice.tts import synthesize
    assert synthesize("Salom") is None


@patch("alisa.voice.tts._mms_available", True)
@patch("alisa.voice.tts._synthesize_mms")
def test_synthesize_uses_mms_first(mock_mms):
    """MMS-TTS is tried first when available."""
    reset_config()
    mock_mms.return_value = "/tmp/alisa_tts/test.wav"

    from alisa.voice.tts import synthesize
    result = synthesize("Salom")

    assert result == "/tmp/alisa_tts/test.wav"
    mock_mms.assert_called_once_with("Salom")


def test_unload_model():
    """unload_model clears global state."""
    from alisa.voice.tts import unload_model
    unload_model()
    from alisa.voice import tts
    assert tts._mms_model is None
