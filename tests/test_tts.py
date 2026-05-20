"""Tests for alisa.voice.tts module."""

from unittest.mock import patch, MagicMock

from alisa.core.config import reset_config


def test_synthesize_empty_text():
    """synthesize returns None for empty text."""
    reset_config()
    from alisa.voice.tts import synthesize
    assert synthesize("") is None
    assert synthesize("   ") is None


@patch("alisa.voice.tts.subprocess.run")
def test_synthesize_success(mock_run):
    """synthesize returns WAV path on success."""
    reset_config()
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

    from alisa.voice.tts import synthesize
    result = synthesize("Salom")

    assert result is not None
    assert result.endswith(".wav")
    assert "/tmp/alisa_tts/" in result
    # Verify piper command
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "/usr/local/bin/piper"
    assert "--model" in cmd


@patch("alisa.voice.tts.subprocess.run")
def test_synthesize_failure(mock_run):
    """synthesize returns None on piper failure."""
    reset_config()
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="err")

    from alisa.voice.tts import synthesize
    result = synthesize("Salom")

    assert result is None


@patch("alisa.voice.tts.subprocess.run")
def test_synthesize_binary_not_found(mock_run):
    """synthesize handles missing binary."""
    reset_config()
    mock_run.side_effect = FileNotFoundError()

    from alisa.voice.tts import synthesize
    result = synthesize("Salom")

    assert result is None
