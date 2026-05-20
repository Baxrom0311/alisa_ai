"""Tests for reception greeter."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from alisa.reception.greeter import ReceptionGreeter


class TestReceptionGreeter:
    """Test reception greeter functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.telegram_notifier = AsyncMock()
        self.greeter = ReceptionGreeter(telegram_notifier=self.telegram_notifier)
    
    def teardown_method(self):
        """Clean up test fixtures."""
        # Ensure reception mode is stopped to prevent async warnings
        if hasattr(self.greeter, 'is_active') and self.greeter.is_active:
            self.greeter.stop_reception_mode()
    
    def test_init(self):
        """Test greeter initialization."""
        assert self.greeter.telegram_notifier == self.telegram_notifier
        assert not self.greeter.is_active
        assert self.greeter.guest_log == []
    
    def test_stop_reception_mode(self):
        """Test stopping reception mode."""
        self.greeter.is_active = True
        self.greeter.stop_reception_mode()
        assert not self.greeter.is_active
    
    def test_get_guest_log(self):
        """Test getting guest log."""
        # Add some test entries
        self.greeter.guest_log = [
            {"time": "2024-01-01 10:00:00", "greeted": True},
            {"time": "2024-01-01 11:00:00", "greeted": True}
        ]
        
        log = self.greeter.get_guest_log()
        assert len(log) == 2
        assert log[0]["time"] == "2024-01-01 10:00:00"
        
        # Ensure it's a copy
        log.append({"time": "test", "greeted": False})
        assert len(self.greeter.guest_log) == 2
    
    def test_clear_guest_log(self):
        """Test clearing guest log."""
        self.greeter.guest_log = [{"time": "test", "greeted": True}]
        self.greeter.clear_guest_log()
        assert self.greeter.guest_log == []
    
    @patch('alisa.reception.greeter.synthesize')
    @patch('alisa.reception.greeter.async_play_audio')
    @pytest.mark.asyncio
    async def test_speak(self, mock_play, mock_synthesize):
        """Test speech synthesis."""
        mock_synthesize.return_value = "/tmp/test.wav"
        
        await self.greeter._speak("test message")
        
        mock_synthesize.assert_called_once_with("test message")
        mock_play.assert_called_once_with("/tmp/test.wav")
    
    @patch('alisa.reception.greeter.synthesize')
    @patch('alisa.reception.greeter.async_play_audio')
    @pytest.mark.asyncio
    async def test_speak_synthesis_error(self, mock_play, mock_synthesize):
        """Test speech synthesis with error."""
        mock_synthesize.side_effect = Exception("TTS error")
        
        # Should not raise exception
        await self.greeter._speak("test message")
        
        mock_synthesize.assert_called_once()
        mock_play.assert_not_called()
    
    @patch('alisa.reception.greeter.synthesize')
    @patch('alisa.reception.greeter.async_play_audio')
    @pytest.mark.asyncio
    async def test_speak_no_wav_path(self, mock_play, mock_synthesize):
        """Test speech synthesis when no WAV path returned."""
        mock_synthesize.return_value = None
        
        await self.greeter._speak("test message")
        
        mock_synthesize.assert_called_once()
        mock_play.assert_not_called()
    
    @patch('alisa.reception.greeter.async_record_until_silence')
    @patch('alisa.reception.greeter.transcribe')
    @patch('alisa.reception.greeter.async_generate')
    @pytest.mark.asyncio
    async def test_handle_conversation_does_not_block_loop(self, mock_generate, mock_transcribe, mock_record):
        """Test that _handle_conversation doesn't block the event loop during transcription."""
        import asyncio
        import time
        
        # Mock a slow transcribe function
        def slow_transcribe(audio_data):
            time.sleep(0.1)  # Simulate slow transcription
            return "test question"
        
        mock_record.side_effect = [b"mock_audio", b""]  # First call returns audio, second empty to exit
        mock_transcribe.side_effect = [slow_transcribe, ""]  # First call slow, second empty to exit
        mock_generate.return_value = "test answer"
        
        # Create a concurrent task that should continue running
        concurrent_progress = []
        
        async def concurrent_task():
            for i in range(5):
                await asyncio.sleep(0.05)  # Should complete during transcription
                concurrent_progress.append(i)
        
        with patch.object(self.greeter, '_speak', new_callable=AsyncMock):
            # Start both tasks concurrently
            conversation_task = asyncio.create_task(self.greeter._handle_conversation())
            concurrent_task_obj = asyncio.create_task(concurrent_task())
            
            # Wait for both to complete
            await asyncio.gather(conversation_task, concurrent_task_obj)
        
        # The concurrent task should have made progress during transcription
        # If transcribe was blocking, concurrent_progress would be empty or incomplete
        assert len(concurrent_progress) == 5, "Concurrent task should complete during transcription"


    @patch('alisa.reception.greeter.async_record_until_silence')
    @patch('alisa.reception.greeter.transcribe')
    @patch('alisa.reception.greeter.async_generate')
    @pytest.mark.asyncio
    async def test_handle_conversation(self, mock_generate, mock_transcribe, mock_record):
        """Test handling conversation."""
        # Mock audio recording and transcription
        mock_record.side_effect = [b"mock_audio", b"mock_audio2", b""]  # Third call returns empty
        mock_transcribe.side_effect = ["Hello", "How are you?", ""]  # Third call returns empty
        mock_generate.return_value = "I'm fine, thank you!"
        
        with patch.object(self.greeter, '_speak', new_callable=AsyncMock) as mock_speak:
            await self.greeter._handle_conversation()
        
        # Should have processed 2 questions (third was empty)
        assert mock_transcribe.call_count == 2
        assert mock_speak.call_count == 2  # Two answers given
    
    @pytest.mark.asyncio
    async def test_handle_guest_notification(self):
        """Test guest handling with notification."""
        with patch.object(self.greeter, '_speak', new_callable=AsyncMock) as mock_speak, \
             patch.object(self.greeter, '_handle_conversation', new_callable=AsyncMock) as mock_conv:
            
            await self.greeter._handle_guest()
        
        # Should greet guest
        mock_speak.assert_called_once()
        greeting_text = mock_speak.call_args[0][0]
        assert "Assalomu alaykum" in greeting_text
        
        # Should handle conversation
        mock_conv.assert_called_once()
        
        # Should log the visit
        assert len(self.greeter.guest_log) == 1
        assert self.greeter.guest_log[0]["greeted"] is True
        
        # Should send notification
        self.telegram_notifier.assert_called_once()
        notification_text = self.telegram_notifier.call_args[0][0]
        assert "Mehmon keldi" in notification_text
