"""Tests for wake word cooldown functionality."""

import asyncio
import time
import pytest
from unittest.mock import patch, AsyncMock

from alisa.core.config import reset_config
from alisa.voice.wake_word import WakeWordDetector


@pytest.mark.asyncio
async def test_confirmation_cooldown_prevents_rapid_calls():
    """_confirm_keyword respects cooldown to prevent rapid STT calls."""
    reset_config()
    
    with patch('alisa.voice.wake_word.get_config') as mock_config:
        mock_config.return_value = {
            "wake_word": {
                "keyword": "alisa",
                "confirmation_cooldown_sec": 2.0  # 2 second cooldown
            }
        }
        
        detector = WakeWordDetector()
        
        with patch('alisa.voice.stt.transcribe') as mock_transcribe:
            mock_transcribe.return_value = "alisa help me"
            
            # First call should work
            result1 = await detector._confirm_keyword(b'dummy_audio')
            assert result1 is True
            assert mock_transcribe.call_count == 1
            
            # Immediate second call should be blocked by cooldown
            result2 = await detector._confirm_keyword(b'dummy_audio')
            assert result2 is False
            assert mock_transcribe.call_count == 1  # No additional call
            
            # After cooldown, should work again
            detector.last_confirmation_attempt = time.time() - 3.0  # Simulate 3s ago
            result3 = await detector._confirm_keyword(b'dummy_audio')
            assert result3 is True
            assert mock_transcribe.call_count == 2  # New call made


@pytest.mark.asyncio
async def test_cooldown_configurable():
    """Cooldown duration is configurable via config."""
    reset_config()
    
    # Test with custom cooldown
    with patch('alisa.voice.wake_word.get_config') as mock_config:
        mock_config.return_value = {
            "wake_word": {
                "keyword": "alisa",
                "confirmation_cooldown_sec": 1.0  # 1 second cooldown
            }
        }
        
        detector = WakeWordDetector()
        assert detector.confirmation_cooldown == 1.0
        
        with patch('alisa.voice.stt.transcribe') as mock_transcribe:
            mock_transcribe.return_value = "alisa help"
            
            # First call
            await detector._confirm_keyword(b'dummy_audio')
            first_attempt_time = detector.last_confirmation_attempt
            
            # Simulate 0.5s later (within cooldown)
            detector.last_confirmation_attempt = time.time() - 0.5
            result = await detector._confirm_keyword(b'dummy_audio')
            assert result is False  # Blocked by cooldown
            
            # Simulate 1.5s later (after cooldown)
            detector.last_confirmation_attempt = time.time() - 1.5
            result = await detector._confirm_keyword(b'dummy_audio')
            assert result is True  # Should work


@pytest.mark.asyncio
async def test_cooldown_default_value():
    """Default cooldown is 5.0 seconds when not specified."""
    reset_config()
    
    with patch('alisa.voice.wake_word.get_config') as mock_config:
        mock_config.return_value = {
            "wake_word": "alisa"  # Flat format, no cooldown specified
        }
        
        detector = WakeWordDetector()
        assert detector.confirmation_cooldown == 5.0  # Default value


@pytest.mark.asyncio
async def test_cooldown_logs_remaining_time():
    """Cooldown logs remaining time when blocking calls."""
    reset_config()
    
    with patch('alisa.voice.wake_word.get_config') as mock_config:
        mock_config.return_value = {
            "wake_word": {
                "keyword": "alisa",
                "confirmation_cooldown_sec": 3.0
            }
        }
        
        detector = WakeWordDetector()
        
        with patch('alisa.voice.stt.transcribe') as mock_transcribe:
            mock_transcribe.return_value = "alisa help"
            
            # First call to set the cooldown
            await detector._confirm_keyword(b'dummy_audio')
            
            # Second call should log remaining time
            with patch('alisa.voice.wake_word.logger') as mock_logger:
                result = await detector._confirm_keyword(b'dummy_audio')
                assert result is False
                
                # Should have logged debug message with remaining time
                mock_logger.debug.assert_called()
                call_args = mock_logger.debug.call_args
                assert call_args[0][0] == "wake_word_confirmation_cooldown"
                assert "remaining" in call_args[1]
                assert call_args[1]["remaining"] > 0
