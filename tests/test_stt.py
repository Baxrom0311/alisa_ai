"""Tests for alisa.voice.stt module."""

from unittest.mock import patch, MagicMock

from alisa.core.config import reset_config


def test_transcribe_empty_bytes():
    """transcribe returns empty string for empty input."""
    reset_config()
    from alisa.voice.stt import transcribe
    assert transcribe(b"") == ""


@patch("alisa.voice.stt.FASTER_WHISPER_AVAILABLE", False)
@patch("alisa.voice.stt.subprocess.run")
def test_transcribe_whisper_cpp_fallback(mock_run):
    """Falls back to whisper.cpp when faster-whisper not available."""
    reset_config()
    mock_run.return_value = MagicMock(returncode=0, stdout="salom dunyo", stderr="")

    from alisa.voice.stt import transcribe
    result = transcribe(b"RIFF" + b"\x00" * 100)

    assert "salom" in result


@patch("alisa.voice.stt.FASTER_WHISPER_AVAILABLE", False)
@patch("alisa.voice.stt.subprocess.run")
def test_transcribe_whisper_cpp_timeout(mock_run):
    """Handles whisper.cpp timeout gracefully."""
    reset_config()
    import subprocess
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="whisper", timeout=30)

    from alisa.voice.stt import transcribe
    result = transcribe(b"RIFF" + b"\x00" * 100)

    assert result == ""


@patch("alisa.voice.stt.FASTER_WHISPER_AVAILABLE", True)
@patch("alisa.voice.stt._get_whisper_model")
def test_transcribe_faster_whisper_with_uzbek_model(mock_get_model):
    """Tests faster-whisper with Uzbek fine-tuned model."""
    reset_config()

    mock_model = MagicMock()
    mock_segment = MagicMock()
    mock_segment.text = "assalomu alaykum"
    mock_info = MagicMock()
    mock_info.language = "uz"
    mock_info.language_probability = 0.95
    mock_model.transcribe.return_value = ([mock_segment], mock_info)
    mock_get_model.return_value = mock_model

    from alisa.voice.stt import transcribe
    result = transcribe(b"RIFF" + b"\x00" * 100)

    assert "assalomu alaykum" in result


def test_unload_model():
    """unload_model clears the global model."""
    from alisa.voice.stt import unload_model
    unload_model()
    from alisa.voice import stt
    assert stt._whisper_model is None
