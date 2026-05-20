"""Tests for STT tmpfs functionality."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from alisa.voice.stt import transcribe


@pytest.fixture
def mock_config():
    """Mock configuration for STT."""
    return {
        "whisper": {
            "binary": "/usr/local/bin/whisper-cli",
            "model": "/opt/alisa/models/ggml-base.en.bin",
            "language": "en"
        }
    }


def test_transcribe_uses_tmpfs_when_available(mock_config):
    """Test that transcribe prefers /dev/shm when available."""
    wav_data = b"fake_wav_data"
    
    with patch("alisa.voice.stt.get_config", return_value=mock_config), \
         patch("os.path.exists") as mock_exists, \
         patch("os.access") as mock_access, \
         patch("tempfile.NamedTemporaryFile") as mock_temp, \
         patch("subprocess.run") as mock_run, \
         patch("pathlib.Path.unlink"):
        
        # Mock /dev/shm as available and writable
        mock_exists.return_value = True
        mock_access.return_value = True
        
        # Mock successful whisper execution
        mock_temp.return_value.__enter__.return_value.name = "/dev/shm/test.wav"
        mock_temp.return_value.__enter__.return_value.write = MagicMock()
        mock_temp.return_value.__enter__.return_value.close = MagicMock()
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "hello world"
        
        result = transcribe(wav_data)
        
        # Verify /dev/shm was checked
        mock_exists.assert_called_with("/dev/shm")
        mock_access.assert_called_with("/dev/shm", os.W_OK)
        
        # Verify tempfile was created with /dev/shm as directory
        mock_temp.assert_called_once_with(suffix=".wav", delete=False, dir="/dev/shm")
        
        assert result == "hello world"


def test_transcribe_falls_back_to_system_temp_when_tmpfs_unavailable(mock_config):
    """Test that transcribe falls back to system temp when /dev/shm is unavailable."""
    wav_data = b"fake_wav_data"
    
    with patch("alisa.voice.stt.get_config", return_value=mock_config), \
         patch("os.path.exists") as mock_exists, \
         patch("tempfile.NamedTemporaryFile") as mock_temp, \
         patch("subprocess.run") as mock_run, \
         patch("pathlib.Path.unlink"):
        
        # Mock /dev/shm as not available
        mock_exists.return_value = False
        
        # Mock successful whisper execution
        mock_temp.return_value.__enter__.return_value.name = "/tmp/test.wav"
        mock_temp.return_value.__enter__.return_value.write = MagicMock()
        mock_temp.return_value.__enter__.return_value.close = MagicMock()
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "hello world"
        
        result = transcribe(wav_data)
        
        # Verify /dev/shm was checked but not used
        mock_exists.assert_called_with("/dev/shm")
        
        # Verify tempfile was created with None (system default) as directory
        mock_temp.assert_called_once_with(suffix=".wav", delete=False, dir=None)
        
        assert result == "hello world"


def test_transcribe_falls_back_when_tmpfs_not_writable(mock_config):
    """Test that transcribe falls back when /dev/shm exists but is not writable."""
    wav_data = b"fake_wav_data"
    
    with patch("alisa.voice.stt.get_config", return_value=mock_config), \
         patch("os.path.exists") as mock_exists, \
         patch("os.access") as mock_access, \
         patch("tempfile.NamedTemporaryFile") as mock_temp, \
         patch("subprocess.run") as mock_run, \
         patch("pathlib.Path.unlink"):
        
        # Mock /dev/shm as existing but not writable
        mock_exists.return_value = True
        mock_access.return_value = False
        
        # Mock successful whisper execution
        mock_temp.return_value.__enter__.return_value.name = "/tmp/test.wav"
        mock_temp.return_value.__enter__.return_value.write = MagicMock()
        mock_temp.return_value.__enter__.return_value.close = MagicMock()
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "hello world"
        
        result = transcribe(wav_data)
        
        # Verify both checks were made
        mock_exists.assert_called_with("/dev/shm")
        mock_access.assert_called_with("/dev/shm", os.W_OK)
        
        # Verify tempfile was created with None (system default) as directory
        mock_temp.assert_called_once_with(suffix=".wav", delete=False, dir=None)
        
        assert result == "hello world"


def test_transcribe_logs_temp_directory_used(mock_config):
    """Test that transcribe logs which temp directory was used."""
    wav_data = b"fake_wav_data"
    
    with patch("alisa.voice.stt.get_config", return_value=mock_config), \
         patch("os.path.exists", return_value=True), \
         patch("os.access", return_value=True), \
         patch("tempfile.NamedTemporaryFile") as mock_temp, \
         patch("subprocess.run") as mock_run, \
         patch("pathlib.Path.unlink"), \
         patch("alisa.voice.stt.logger") as mock_logger:
        
        # Mock successful whisper execution
        mock_temp.return_value.__enter__.return_value.name = "/dev/shm/test.wav"
        mock_temp.return_value.__enter__.return_value.write = MagicMock()
        mock_temp.return_value.__enter__.return_value.close = MagicMock()
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "hello world"
        
        result = transcribe(wav_data)
        
        # Verify logging includes temp directory info
        mock_logger.info.assert_called_with("stt_done", text_len=11, temp_dir="/dev/shm")
        
        assert result == "hello world"
