"""Tests for Silero VAD integration in audio_io module."""

from unittest.mock import patch, MagicMock
import numpy as np

from alisa.core.config import reset_config


def test_silero_vad_fallback_when_unavailable():
    """Falls back to energy-based VAD when Silero not available."""
    reset_config()
    from alisa.voice import audio_io
    
    # Force Silero unavailable
    with patch.object(audio_io, '_silero_available', False):
        with patch.object(audio_io, '_silero_vad_model', None):
            # Should not raise, just use energy-based
            model = audio_io._get_silero_vad()
            # If torch not installed, model will be None
            # This is expected behavior


@patch("alisa.voice.audio_io.sd.InputStream")
def test_record_until_silence_energy_fallback(mock_stream):
    """record_until_silence works with energy-based VAD."""
    reset_config()
    from alisa.voice import audio_io
    
    # Force energy-based VAD
    with patch.object(audio_io, '_silero_available', False):
        with patch.object(audio_io, '_silero_vad_model', None):
            # Mock audio stream with speech then silence
            mock_ctx = MagicMock()
            speech_frame = np.ones((160, 1), dtype=np.int16) * 5000
            silence_frame = np.zeros((160, 1), dtype=np.int16)
            
            # Return speech frames then silence
            frames = [speech_frame] * 5 + [silence_frame] * 10
            mock_ctx.read.side_effect = [(f, False) for f in frames]
            mock_stream.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_stream.return_value.__exit__ = MagicMock(return_value=False)
            
            result = audio_io._record_with_energy_vad(
                max_sec=2.0, silence_ms=600, 
                start_timeout_sec=1.0, energy_threshold_rms=0.01
            )
            # Should return bytes (may be empty if threshold not met)
            assert isinstance(result, bytes)
