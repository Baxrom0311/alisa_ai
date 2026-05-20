"""Tests for alisa.voice.audio_io module."""

import asyncio
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from alisa.core.config import reset_config


@patch("alisa.voice.audio_io.sd")
def test_record_audio_returns_wav_bytes(mock_sd):
    """record_audio returns valid WAV bytes."""
    reset_config()
    # Mock sounddevice to return silence
    mock_sd.rec.return_value = np.zeros((16000,), dtype="int16")
    mock_sd.wait.return_value = None

    from alisa.voice.audio_io import record_audio
    result = record_audio(duration_sec=1.0)

    assert len(result) > 44  # WAV header is 44 bytes
    assert result[:4] == b"RIFF"
    mock_sd.rec.assert_called_once()


@patch("alisa.voice.audio_io.sd")
def test_record_audio_handles_error(mock_sd):
    """record_audio returns empty bytes on error."""
    reset_config()
    mock_sd.rec.side_effect = RuntimeError("No device")

    from alisa.voice.audio_io import record_audio
    result = record_audio()

    assert result == b""


@patch("alisa.voice.audio_io.sd")
def test_play_audio(mock_sd, tmp_path):
    """play_audio calls sounddevice.play."""
    reset_config()
    import wave
    wav_path = str(tmp_path / "test.wav")
    with wave.open(wav_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(np.zeros(1600, dtype="int16").tobytes())

    from alisa.voice.audio_io import play_audio
    mock_sd.wait.return_value = None
    play_audio(wav_path)

    mock_sd.play.assert_called_once()


@pytest.mark.asyncio
@patch("alisa.voice.audio_io.sd")
async def test_async_record_audio_returns_wav_bytes(mock_sd):
    """async_record_audio returns valid WAV bytes."""
    reset_config()
    # Mock sounddevice to return silence
    mock_sd.rec.return_value = np.zeros((16000,), dtype="int16")
    mock_sd.wait.return_value = None

    from alisa.voice.audio_io import async_record_audio
    result = await async_record_audio(duration_sec=1.0)

    assert len(result) > 44  # WAV header is 44 bytes
    assert result[:4] == b"RIFF"
    mock_sd.rec.assert_called_once()


@pytest.mark.asyncio
@patch("alisa.voice.audio_io.sd")
async def test_async_play_audio(mock_sd, tmp_path):
    """async_play_audio calls sounddevice.play."""
    reset_config()
    import wave
    wav_path = str(tmp_path / "test.wav")
    with wave.open(wav_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(np.zeros(1600, dtype="int16").tobytes())

    from alisa.voice.audio_io import async_play_audio
    mock_sd.wait.return_value = None
    await async_play_audio(wav_path)

    mock_sd.play.assert_called_once()


@pytest.mark.asyncio
async def test_async_functions_do_not_block():
    """Async variants do not block the event loop."""
    import time
    
    # Create a task that should run concurrently
    start_time = time.time()
    concurrent_task_ran = False
    
    async def concurrent_task():
        nonlocal concurrent_task_ran
        await asyncio.sleep(0.1)  # Short delay
        concurrent_task_ran = True
    
    # Mock slow audio operations
    with patch("alisa.voice.audio_io.record_audio") as mock_record, \
         patch("alisa.voice.audio_io.play_audio") as mock_play:
        
        # Make sync functions slow
        def slow_record(*args, **kwargs):
            time.sleep(0.2)
            return b"RIFF" + b"\x00" * 40
        
        def slow_play(*args, **kwargs):
            time.sleep(0.2)
        
        mock_record.side_effect = slow_record
        mock_play.side_effect = slow_play
        
        from alisa.voice.audio_io import async_record_audio, async_play_audio
        
        # Run async functions concurrently with another task
        await asyncio.gather(
            async_record_audio(1.0),
            async_play_audio("/fake/path.wav"),
            concurrent_task()
        )
    
    # Verify concurrent task ran (proving no blocking)
    assert concurrent_task_ran
    elapsed = time.time() - start_time
    # Should take around 0.2s (not 0.4s if blocking)
    assert elapsed < 0.3
