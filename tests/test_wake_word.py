"""Tests for wake word detection module."""

import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from alisa.core.config import reset_config, get_config
from alisa.voice.wake_word import WakeWordDetector, detect_wake_word, OPENWAKEWORD_AVAILABLE


def test_wake_word_detector_init():
    """WakeWordDetector initializes with config values."""
    reset_config()
    detector = WakeWordDetector()
    assert detector.keyword == "alisa"
    assert detector.sensitivity == 0.05
    assert not detector.is_listening


def test_wake_word_detector_init_defaults():
    """WakeWordDetector uses defaults when config is missing."""
    reset_config()
    
    # Mock minimal config
    with patch('alisa.voice.wake_word.get_config') as mock_config:
        mock_config.return_value = {"wake_word": {}}
        
        detector = WakeWordDetector()
        assert detector.keyword == "alisa"  # Default
        assert detector.sensitivity == 0.05  # Default
        assert detector.confirmation_cooldown == 5.0  # Default
        assert detector.method == "auto"  # Default
        assert detector.oww_model_name == "alexa"  # Default
        assert detector.oww_framework == "onnx"  # Default
        assert detector.energy_threshold == 500  # Default
        assert detector.min_duration_ms == 100  # Default


def test_wake_word_detector_init_explicit_config():
    """WakeWordDetector handles explicit nested wake_word config format."""
    reset_config()
    
    # Mock explicit config format
    with patch('alisa.voice.wake_word.get_config') as mock_config:
        mock_config.return_value = {
            "wake_word": {
                "keyword": "custom_keyword",
                "sensitivity": 0.1,
                "confirmation_cooldown_sec": 3.0,
                "method": "openwakeword",
                "openwakeword": {
                    "model": "custom_model",
                    "inference_framework": "tflite"
                },
                "energy_gated": {
                    "threshold": 1000,
                    "min_duration_ms": 200
                }
            }
        }
        
        detector = WakeWordDetector()
        assert detector.keyword == "custom_keyword"
        assert detector.sensitivity == 0.1
        assert detector.confirmation_cooldown == 3.0
        assert detector.method == "openwakeword"
        assert detector.oww_model_name == "custom_model"
        assert detector.oww_framework == "tflite"
        assert detector.energy_threshold == 1000
        assert detector.min_duration_ms == 200


def test_wake_word_method_selection():
    """WakeWordDetector selects correct method based on config and availability."""
    reset_config()
    
    # Test energy_gated method (should not try openwakeword)
    with patch('alisa.voice.wake_word.get_config') as mock_config:
        mock_config.return_value = {
            "wake_word": {"method": "energy_gated"}
        }
        
        detector = WakeWordDetector()
        assert detector.method == "energy_gated"
        assert detector.oww_model is None  # Should not have openwakeword model
    
    # Test auto method with openwakeword unavailable (fallback to energy_gated)
    with patch('alisa.voice.wake_word.get_config') as mock_config, \
         patch('alisa.voice.wake_word.OPENWAKEWORD_AVAILABLE', False):
        
        mock_config.return_value = {
            "wake_word": {"method": "auto"}
        }
        
        detector = WakeWordDetector()
        assert detector.method == "auto"
        assert detector.oww_model is None  # Should fallback to energy_gated


@pytest.mark.asyncio
async def test_wake_word_uses_config_keyword_in_confirmation():
    """_confirm_keyword uses the configured keyword, not hardcoded."""
    reset_config()
    
    with patch('alisa.voice.wake_word.get_config') as mock_config:
        mock_config.return_value = {
            "wake_word": "test_keyword"
        }
        
        detector = WakeWordDetector()
        
        with patch('alisa.voice.stt.transcribe') as mock_transcribe:
            # Should match configured keyword
            mock_transcribe.return_value = "hey test_keyword help me"
            result = await detector._confirm_keyword(b'dummy_audio')
            assert result is True
            
            # Should not match different keyword
            detector.last_confirmation_attempt = 0  # Reset cooldown
            mock_transcribe.return_value = "hey alisa help me"
            result = await detector._confirm_keyword(b'dummy_audio')
            assert result is False


def test_wake_word_warns_when_using_alexa_proxy():
    """WakeWordDetector warns when using alexa model for non-alexa keyword."""
    reset_config()
    
    if not OPENWAKEWORD_AVAILABLE:
        pytest.skip("openWakeWord not available")
    
    with patch('alisa.voice.wake_word.get_config') as mock_config:
        mock_config.return_value = {
            "wake_word": {
                "keyword": "alisa",
                "model": "alexa"
            }
        }
        
        with patch('alisa.voice.wake_word.Model') as mock_model:
            mock_model.return_value = MagicMock()
            
            with patch('alisa.voice.wake_word.logger') as mock_logger:
                detector = WakeWordDetector()
                
                # Should emit warning when model != keyword
                mock_logger.warning.assert_called_with(
                    "wake_word_model_proxy",
                    configured_keyword="alisa",
                    oww_model="alexa", 
                    message="Using 'alexa' model as phonetic proxy for 'alisa'"
                )


def test_wake_word_detector_init_with_openwakeword():
    """WakeWordDetector handles openWakeWord initialization."""
    reset_config()
    
    if OPENWAKEWORD_AVAILABLE:
        # If openWakeWord is available, it should try to initialize
        with patch('alisa.voice.wake_word.Model') as mock_model:
            mock_model.return_value = MagicMock()
            detector = WakeWordDetector()
            assert detector.oww_model is not None
    else:
        # If not available, should fall back gracefully
        detector = WakeWordDetector()
        assert detector.oww_model is None


def test_has_sufficient_energy():
    """_has_sufficient_energy returns True for high energy audio."""
    reset_config()
    detector = WakeWordDetector()
    
    # High energy audio (loud samples)
    loud_audio = b'\xff\x7f' * 1000  # Max positive 16-bit samples
    assert detector._has_sufficient_energy(loud_audio)
    
    # Low energy audio (quiet samples)
    quiet_audio = b'\x00\x00' * 1000  # Silent samples
    assert not detector._has_sufficient_energy(quiet_audio)


@pytest.mark.asyncio
async def test_detect_with_openwakeword():
    """_detect_with_openwakeword processes audio correctly."""
    reset_config()
    
    # Mock the detector with openWakeWord model
    detector = WakeWordDetector()
    mock_model = MagicMock()
    mock_model.predict.return_value = {"alexa": 0.8}
    detector.oww_model = mock_model
    
    # Test with dummy audio data
    audio_data = b'\x00\x01' * 1000
    
    with patch('numpy.array') as mock_array:
        mock_array.return_value = MagicMock()
        result = await detector._detect_with_openwakeword(audio_data)
        
        # Should detect with score 0.8 > sensitivity 0.05
        assert result is True


@pytest.mark.asyncio
async def test_confirm_keyword_with_match():
    """_confirm_keyword returns True when transcript contains keyword."""
    reset_config()
    detector = WakeWordDetector()
    
    with patch('alisa.voice.stt.transcribe') as mock_transcribe:
        mock_transcribe.return_value = "alisa qanday yordam"
        
        result = await detector._confirm_keyword(b'dummy_audio')
        assert result is True


@pytest.mark.asyncio
async def test_confirm_keyword_without_match():
    """_confirm_keyword returns False when transcript doesn't contain keyword."""
    reset_config()
    detector = WakeWordDetector()
    
    with patch('alisa.voice.stt.transcribe') as mock_transcribe:
        mock_transcribe.return_value = "salom dunyo"
        
        result = await detector._confirm_keyword(b'dummy_audio')
        assert result is False


@pytest.mark.asyncio
async def test_confirm_keyword_with_variants():
    """_confirm_keyword recognizes keyword variants."""
    reset_config()
    detector = WakeWordDetector()
    
    variants = ["alisa,", "alisa.", "alisa!", "alisa?"]
    
    for variant in variants:
        # Reset cooldown for each variant test
        detector.last_confirmation_attempt = 0
        
        with patch('alisa.voice.stt.transcribe') as mock_transcribe:
            mock_transcribe.return_value = f"hey {variant} help me"
            
            result = await detector._confirm_keyword(b'dummy_audio')
            assert result is True, f"Should recognize variant: {variant}"


@pytest.mark.asyncio
@patch('alisa.voice.wake_word.record_audio')
async def test_start_listening_energy_gated(mock_record):
    """start_listening only transcribes when energy threshold is met."""
    reset_config()
    detector = WakeWordDetector()
    callback = AsyncMock()
    
    # Mock low energy audio (should not trigger transcription)
    mock_record.return_value = b'\x00\x00' * 1000
    
    with patch.object(detector, '_confirm_keyword') as mock_confirm:
        # Start listening in background
        listen_task = asyncio.create_task(detector.start_listening(callback))
        
        # Give it time to process
        await asyncio.sleep(0.2)
        
        # Stop listening
        detector.stop_listening()
        await listen_task
        
        # Transcription should not have been called due to low energy
        mock_confirm.assert_not_called()
        callback.assert_not_called()


@pytest.mark.asyncio
@patch('alisa.voice.wake_word.record_audio')
async def test_start_listening_with_confirmation(mock_record):
    """start_listening calls callback when keyword is confirmed."""
    reset_config()
    detector = WakeWordDetector()
    callback = AsyncMock()
    
    # Mock high energy audio
    mock_record.return_value = b'\xff\x7f' * 1000
    
    with patch.object(detector, '_confirm_keyword', return_value=True) as mock_confirm:
        # Start listening in background
        listen_task = asyncio.create_task(detector.start_listening(callback))
        
        # Give it time to detect
        await asyncio.sleep(0.2)
        
        # Stop listening
        detector.stop_listening()
        await listen_task
        
        # Both energy check and keyword confirmation should have happened
        mock_confirm.assert_called()
        callback.assert_called()


@pytest.mark.asyncio
@patch('alisa.voice.wake_word.record_audio')
async def test_detect_wake_word_function(mock_record):
    """detect_wake_word convenience function works."""
    reset_config()
    callback = AsyncMock()
    
    # Mock high energy audio
    mock_record.return_value = b'\xff\x7f' * 1000
    
    with patch('alisa.voice.stt.transcribe', return_value="alisa help"):
        # Start detection
        detect_task = asyncio.create_task(detect_wake_word(callback))
        
        # Give it time to detect
        await asyncio.sleep(0.2)
        
        # Cancel the task
        detect_task.cancel()
        
        try:
            await detect_task
        except asyncio.CancelledError:
            pass
        
        # Callback should have been called
        callback.assert_called()
