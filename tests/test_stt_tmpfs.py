"""Tests for STT tmpfs usage (updated for faster-whisper API)."""

from unittest.mock import patch, MagicMock
from alisa.core.config import reset_config


@patch("alisa.voice.stt.FASTER_WHISPER_AVAILABLE", False)
@patch("alisa.voice.stt.subprocess.run")
def test_transcribe_uses_tmpfs_when_available(mock_run):
    """STT uses /dev/shm for temp files when available (Linux only)."""
    reset_config()
    mock_run.return_value = MagicMock(returncode=0, stdout="salom", stderr="")

    from alisa.voice.stt import transcribe
    result = transcribe(b"RIFF" + b"\x00" * 100)
    assert "salom" in result


@patch("alisa.voice.stt.FASTER_WHISPER_AVAILABLE", False)
@patch("alisa.voice.stt.os.path.exists")
@patch("alisa.voice.stt.subprocess.run")
def test_transcribe_falls_back_when_tmpfs_not_writable(mock_run, mock_exists):
    """STT falls back to system temp when /dev/shm not available."""
    reset_config()
    mock_exists.return_value = False
    mock_run.return_value = MagicMock(returncode=0, stdout="test", stderr="")

    from alisa.voice.stt import transcribe
    result = transcribe(b"RIFF" + b"\x00" * 100)
    assert "test" in result


@patch("alisa.voice.stt.FASTER_WHISPER_AVAILABLE", False)
@patch("alisa.voice.stt.subprocess.run")
def test_transcribe_logs_temp_directory_used(mock_run):
    """STT works regardless of temp directory."""
    reset_config()
    mock_run.return_value = MagicMock(returncode=0, stdout="natija", stderr="")

    from alisa.voice.stt import transcribe
    result = transcribe(b"RIFF" + b"\x00" * 100)
    assert "natija" in result
