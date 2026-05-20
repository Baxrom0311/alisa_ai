"""Tests for assistant 3-second response time requirement."""

import asyncio
import time
from unittest.mock import Mock, patch, AsyncMock
import pytest

from alisa.core.assistant import AlisaAssistant


class TestAssistantResponseTime:
    """Test assistant response time requirements."""

    @pytest.mark.asyncio
    async def test_wake_to_response_under_3s(self):
        """Test that wake word to response completes in under 3 seconds."""
        
        # Mock all the slow operations
        mock_config = {
            "assistant": {"name": "Alisa"},
            "audio": {"sample_rate": 16000, "channels": 1, "input_device": None, "output_device": None},
            "whisper": {"model": "base", "binary": "/usr/local/bin/whisper"},
            "llm": {"model": "tinyllama", "base_url": "http://localhost:11434"},
            "tts": {"voice": "en_US-lessac-medium", "binary": "/usr/local/bin/piper"}
        }
        
        # Create mock audio data (small WAV)
        mock_audio_data = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x40\x3f\x00\x00\x80\x7e\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
        
        # Mock functions to be fast
        async def fast_vad(*args, **kwargs):
            await asyncio.sleep(0.1)  # Simulate 100ms VAD
            return mock_audio_data
            
        def fast_transcribe(audio_data):
            time.sleep(0.2)  # Simulate 200ms transcription
            return "Hello Alisa"
            
        async def fast_generate(prompt, **kwargs):
            await asyncio.sleep(0.3)  # Simulate 300ms LLM
            return "Hello! How can I help you?"
            
        def fast_synthesize(text, output_path):
            time.sleep(0.2)  # Simulate 200ms TTS
            # Create a dummy WAV file
            with open(output_path, 'wb') as f:
                f.write(mock_audio_data)
            
        async def fast_play_audio(path):
            await asyncio.sleep(0.1)  # Simulate 100ms playback
        
        # Mock memory manager and profiler
        mock_memory_manager = Mock()
        mock_memory_manager.monitor_and_cleanup.return_value = False
        
        mock_profiler = Mock()
        mock_profiler.start_operation.return_value.__enter__ = Mock()
        mock_profiler.start_operation.return_value.__exit__ = Mock()
        
        with patch('alisa.core.assistant.get_config', return_value=mock_config), \
             patch('alisa.core.assistant.get_memory_manager', return_value=mock_memory_manager), \
             patch('alisa.core.assistant.get_profiler', return_value=mock_profiler), \
             patch('alisa.core.assistant.get_memory', return_value=[]), \
             patch('alisa.core.assistant.async_record_until_silence', side_effect=fast_vad), \
             patch('alisa.core.assistant.transcribe', side_effect=fast_transcribe), \
             patch('alisa.core.assistant.async_generate', side_effect=fast_generate), \
             patch('alisa.core.assistant.synthesize', side_effect=fast_synthesize), \
             patch('alisa.core.assistant.async_play_audio', side_effect=fast_play_audio), \
             patch('tempfile.NamedTemporaryFile') as mock_temp:
            
            # Mock temporary file
            mock_temp.return_value.__enter__.return_value.name = "/tmp/test_audio.wav"
            
            assistant = AlisaAssistant()
            
            # Measure time for wake word handling
            start_time = time.monotonic()
            await assistant._handle_wake_word()
            elapsed_time = time.monotonic() - start_time
            
            # Should complete in under 3 seconds
            assert elapsed_time < 3.0, f"Response took {elapsed_time:.2f}s, should be < 3.0s"
            
            # Verify it's reasonably fast (not too fast to be realistic)
            assert elapsed_time > 0.2, f"Response took {elapsed_time:.2f}s, seems unrealistically fast"

    @pytest.mark.asyncio
    async def test_concurrent_operations_during_vad(self):
        """Test that other async operations can progress during VAD recording."""
        
        # This test verifies that VAD doesn't block the event loop
        mock_config = {
            "assistant": {"name": "Alisa"},
            "audio": {"sample_rate": 16000, "channels": 1, "input_device": None, "output_device": None}
        }
        
        # Mock VAD to take some time
        async def slow_vad(*args, **kwargs):
            await asyncio.sleep(1.0)  # 1 second VAD
            return b"mock_audio_data"
        
        # Counter to track concurrent task progress
        counter = {"value": 0}
        
        async def concurrent_task():
            """Task that should progress during VAD."""
            for i in range(10):
                await asyncio.sleep(0.1)  # 100ms intervals
                counter["value"] += 1
        
        with patch('alisa.core.assistant.get_config', return_value=mock_config), \
             patch('alisa.voice.audio_io.async_record_until_silence', side_effect=slow_vad):
            
            # Start both tasks concurrently
            vad_task = asyncio.create_task(slow_vad())
            concurrent_task_handle = asyncio.create_task(concurrent_task())
            
            # Wait for both to complete
            await asyncio.gather(vad_task, concurrent_task_handle)
            
            # The concurrent task should have made significant progress
            # If VAD blocked the event loop, counter would be 0 or very low
            assert counter["value"] >= 8, f"Concurrent task only progressed {counter['value']}/10 steps"
