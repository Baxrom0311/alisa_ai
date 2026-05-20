"""Tests for alisa.voice.stt module."""

from unittest.mock import patch, MagicMock

from alisa.core.config import reset_config


def test_transcribe_empty_bytes():
    """transcribe returns empty string for empty input."""
    reset_config()
    from alisa.voice.stt import transcribe
    assert transcribe(b"") == ""


@patch("alisa.voice.stt.subprocess.run")
def test_transcribe_success(mock_run):
    """transcribe returns text from whisper stdout."""
    reset_config()
    mock_run.return_value = MagicMock(
        returncode=0, stdout="Salom dunyo", stderr=""
    )

    from alisa.voice.stt import transcribe
    result = transcribe(b"RIFF" + b"\x00" * 100)

    assert result == "Salom dunyo"
    mock_run.assert_called_once()
    # Verify whisper binary is called
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "/usr/local/bin/whisper-cli"


@patch("alisa.voice.stt.subprocess.run")
def test_transcribe_failure(mock_run):
    """transcribe returns empty string on whisper failure."""
    reset_config()
    mock_run.return_value = MagicMock(
        returncode=1, stdout="", stderr="error"
    )

    from alisa.voice.stt import transcribe
    result = transcribe(b"RIFF" + b"\x00" * 100)

    assert result == ""


@patch("alisa.voice.stt.subprocess.run")
def test_transcribe_timeout(mock_run):
    """transcribe handles timeout gracefully."""
    reset_config()
    import subprocess
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="whisper", timeout=30)

    from alisa.voice.stt import transcribe
    result = transcribe(b"RIFF" + b"\x00" * 100)

    assert result == ""
