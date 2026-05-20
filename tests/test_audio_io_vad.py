"""Tests for VAD (Voice Activity Detection) in audio_io module."""

import asyncio
import io
import wave
from unittest.mock import Mock, patch, MagicMock
import numpy as np
import pytest

from alisa.voice.audio_io import record_until_silence, async_record_until_silence


class TestVAD:
    """Test Voice Activity Detection functionality."""

    def test_record_until_silence_with_synthetic_audio(self):
        """Test VAD with synthetic sine wave followed by silence."""
        # Mock config
        mock_config = {
            "audio": {
                "sample_rate": 16000,
                "channels": 1,
                "input_device": None
            }
        }
        
        # Create synthetic audio: 0.5s of sine wave (speech) + 0.7s of silence
        sample_rate = 16000
        frame_size = 1600  # 100ms at 16kHz
        
        # Generate frames: 5 frames of sine wave + 7 frames of silence
        sine_frames = []
        silence_frames = []
        
        for i in range(5):  # 500ms of speech
            t = np.linspace(i * 0.1, (i + 1) * 0.1, frame_size)
            sine_wave = (np.sin(2 * np.pi * 440 * t) * 16000).astype(np.int16)  # Louder signal
            sine_frames.append(sine_wave.reshape(-1, 1))
            
        for i in range(7):  # 700ms of silence
            silence_wave = (np.random.normal(0, 10, frame_size)).astype(np.int16)  # Low noise
            silence_frames.append(silence_wave.reshape(-1, 1))
        
        all_frames = sine_frames + silence_frames
        
        # Mock sounddevice.InputStream
        mock_stream = MagicMock()
        mock_stream.__enter__ = Mock(return_value=mock_stream)
        mock_stream.__exit__ = Mock(return_value=None)
        
        # Make read() return frames sequentially
        mock_stream.read.side_effect = [(frame, False) for frame in all_frames]
        
        with patch('alisa.voice.audio_io.get_config', return_value=mock_config), \
             patch('alisa.voice.audio_io.sd.InputStream', return_value=mock_stream):
            
            result = record_until_silence(
                max_sec=3.0,
                silence_ms=600,  # Should stop after 6 frames of silence
                start_timeout_sec=1.0,
                energy_threshold_rms=0.1  # Lower threshold
            )
        
        # Should have recorded something (not empty)
        assert len(result) > 0
        
        # Should be valid WAV data
        buf = io.BytesIO(result)
        with wave.open(buf, 'rb') as wf:
            assert wf.getnchannels() == 1
            assert wf.getframerate() == 16000
            assert wf.getnframes() > 0

    def test_record_until_silence_timeout(self):
        """Test VAD timeout when no speech is detected."""
        mock_config = {
            "audio": {
                "sample_rate": 16000,
                "channels": 1,
                "input_device": None
            }
        }
        
        # Generate only silence frames
        frame_size = 1600
        silence_frames = []
        for i in range(20):  # 2 seconds of silence
            silence_wave = (np.random.normal(0, 10, frame_size)).astype(np.int16)
            silence_frames.append(silence_wave.reshape(-1, 1))
        
        mock_stream = MagicMock()
        mock_stream.__enter__ = Mock(return_value=mock_stream)
        mock_stream.__exit__ = Mock(return_value=None)
        mock_stream.read.side_effect = [(frame, False) for frame in silence_frames]
        
        with patch('alisa.voice.audio_io.get_config', return_value=mock_config), \
             patch('alisa.voice.audio_io.sd.InputStream', return_value=mock_stream):
            
            result = record_until_silence(
                max_sec=3.0,
                silence_ms=600,
                start_timeout_sec=1.0,  # Should timeout after 1 second
                energy_threshold_rms=0.1
            )
        
        # Should return empty bytes due to timeout
        assert result == b""

    def test_record_until_silence_max_duration(self):
        """Test VAD hard cap at max_sec."""
        mock_config = {
            "audio": {
                "sample_rate": 16000,
                "channels": 1,
                "input_device": None
            }
        }
        
        # Generate continuous speech (no silence)
        frame_size = 1600
        speech_frames = []
        for i in range(50):  # 5 seconds of continuous speech
            t = np.linspace(i * 0.1, (i + 1) * 0.1, frame_size)
            sine_wave = (np.sin(2 * np.pi * 440 * t) * 16000).astype(np.int16)
            speech_frames.append(sine_wave.reshape(-1, 1))
        
        mock_stream = MagicMock()
        mock_stream.__enter__ = Mock(return_value=mock_stream)
        mock_stream.__exit__ = Mock(return_value=None)
        mock_stream.read.side_effect = [(frame, False) for frame in speech_frames]
        
        with patch('alisa.voice.audio_io.get_config', return_value=mock_config), \
             patch('alisa.voice.audio_io.sd.InputStream', return_value=mock_stream):
            
            result = record_until_silence(
                max_sec=2.0,  # Should stop after 2 seconds
                silence_ms=600,
                start_timeout_sec=1.0,
                energy_threshold_rms=0.1
            )
        
        # Should have recorded something but stopped at max_sec
        assert len(result) > 0
        
        # Verify duration is approximately 2 seconds
        buf = io.BytesIO(result)
        with wave.open(buf, 'rb') as wf:
            duration = wf.getnframes() / wf.getframerate()
            assert 1.8 <= duration <= 2.2  # Allow some tolerance

    @pytest.mark.asyncio
    async def test_async_record_until_silence(self):
        """Test async wrapper for VAD."""
        mock_config = {
            "audio": {
                "sample_rate": 16000,
                "channels": 1,
                "input_device": None
            }
        }
        
        # Simple test with immediate silence detection
        frame_size = 1600
        frames = []
        
        # 2 frames of speech + 7 frames of silence
        for i in range(2):
            t = np.linspace(i * 0.1, (i + 1) * 0.1, frame_size)
            sine_wave = (np.sin(2 * np.pi * 440 * t) * 16000).astype(np.int16)
            frames.append(sine_wave.reshape(-1, 1))
            
        for i in range(7):
            silence_wave = (np.random.normal(0, 10, frame_size)).astype(np.int16)
            frames.append(silence_wave.reshape(-1, 1))
        
        mock_stream = MagicMock()
        mock_stream.__enter__ = Mock(return_value=mock_stream)
        mock_stream.__exit__ = Mock(return_value=None)
        mock_stream.read.side_effect = [(frame, False) for frame in frames]
        
        with patch('alisa.voice.audio_io.get_config', return_value=mock_config), \
             patch('alisa.voice.audio_io.sd.InputStream', return_value=mock_stream):
            
            result = await async_record_until_silence(
                max_sec=3.0,
                silence_ms=600,
                start_timeout_sec=1.0,
                energy_threshold_rms=0.1
            )
        
        assert len(result) > 0
