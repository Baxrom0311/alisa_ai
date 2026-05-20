"""Tests for main assistant module."""

import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

from alisa.core.config import reset_config
from alisa.core.assistant import AlisaAssistant, ALISA_SYSTEM_PROMPT_UZ


def test_assistant_init():
    """AlisaAssistant initializes correctly."""
    reset_config()
    assistant = AlisaAssistant()
    assert not assistant.is_running
    assert assistant.config is not None


@pytest.mark.asyncio
@patch('alisa.core.assistant.detect_wake_word')
async def test_assistant_start_stop(mock_detect):
    """Assistant starts and stops correctly."""
    reset_config()
    assistant = AlisaAssistant()
    
    # Mock wake word detection to return immediately
    mock_detect.return_value = None
    
    # Start assistant in background
    start_task = asyncio.create_task(assistant.start())
    
    # Give it time to start
    await asyncio.sleep(0.1)
    
    # Stop assistant
    assistant.stop()
    
    # Wait for task to complete
    await start_task
    
    assert not assistant.is_running


@pytest.mark.asyncio
async def test_process_text():
    """process_text generates response for text input."""
    reset_config()
    assistant = AlisaAssistant()
    
    # Mock the LLMManager's generate method
    with patch.object(assistant.llm_manager, 'generate', new_callable=AsyncMock) as mock_generate:
        mock_generate.return_value = "Salom! Qanday yordam bera olaman?"
        
        response = await assistant.process_text("Salom Alisa")
        
        assert response == "Salom! Qanday yordam bera olaman?"
        mock_generate.assert_called_once()


@pytest.mark.asyncio
async def test_process_text_error_handling():
    """process_text handles errors gracefully."""
    reset_config()
    assistant = AlisaAssistant()
    
    # Mock the LLM manager to raise an exception
    with patch.object(assistant.llm_manager, 'generate', side_effect=Exception("LLM error")):
        response = await assistant.process_text("test")
        
        assert response == "Kechirasiz, javob bera olmadim."


@pytest.mark.asyncio
@patch('alisa.core.assistant.Path')
@patch('alisa.core.assistant.async_play_audio')
@patch('alisa.core.assistant.synthesize')
@patch('alisa.core.assistant.transcribe')
@patch('alisa.core.assistant.async_record_until_silence')
async def test_handle_wake_word(mock_record, mock_transcribe, 
                               mock_synthesize, mock_play, mock_path):
    """_handle_wake_word processes full conversation flow."""
    reset_config()
    assistant = AlisaAssistant()
    
    # Mock the full pipeline with AsyncMock for async operations
    mock_record.return_value = b"fake_audio_data"
    mock_transcribe.return_value = "Salom Alisa"
    mock_synthesize.return_value = "/tmp/response.wav"
    
    # Mock Path operations
    mock_path_obj = MagicMock()
    mock_path_obj.exists.return_value = True
    mock_path.return_value = mock_path_obj
    
    # Mock the LLMManager's generate method
    with patch.object(assistant.llm_manager, 'generate', new_callable=AsyncMock) as mock_generate:
        mock_generate.return_value = "Salom! Qanday yordam bera olaman?"
        
        # Call the wake word handler
        await assistant._handle_wake_word()
        
        # Verify the pipeline was called
        mock_record.assert_called_once()  # VAD function called with default params
        mock_transcribe.assert_called_once_with(b"fake_audio_data")
        mock_generate.assert_called_once()
        mock_synthesize.assert_called_once_with("Salom! Qanday yordam bera olaman?")
        mock_play.assert_called_once_with("/tmp/response.wav")
        mock_path_obj.unlink.assert_called_once_with(missing_ok=True)


@pytest.mark.asyncio
@patch('alisa.core.assistant.transcribe')
@patch('alisa.core.assistant.async_record_until_silence')
async def test_handle_wake_word_no_speech(mock_record, mock_transcribe):
    """_handle_wake_word handles empty transcription."""
    reset_config()
    assistant = AlisaAssistant()
    
    mock_record.return_value = b"fake_audio_data"
    mock_transcribe.return_value = ""  # Empty transcription
    
    # Should return early without generating response
    await assistant._handle_wake_word()
    
    mock_record.assert_called_once()
    mock_transcribe.assert_called_once()


@pytest.mark.asyncio
@patch('alisa.core.assistant.Path')
@patch('alisa.core.assistant.async_play_audio')
@patch('alisa.core.assistant.synthesize')
@patch('alisa.core.assistant.transcribe')
@patch('alisa.core.assistant.async_record_audio')
async def test_handle_wake_word_uses_memory(mock_record, mock_transcribe, 
                                          mock_synthesize, mock_play, mock_path):
    """_handle_wake_word adds messages to conversation memory."""
    reset_config()
    assistant = AlisaAssistant()
    
    # Mock the full pipeline
    mock_record.return_value = b"fake_audio_data"
    mock_transcribe.return_value = "Salom Alisa"
    mock_synthesize.return_value = "/tmp/response.wav"
    
    # Mock Path operations
    mock_path_obj = MagicMock()
    mock_path_obj.exists.return_value = True
    mock_path.return_value = mock_path_obj
    
    # Clear memory first
    assistant.memory.clear()
    
    # Mock the LLMManager's generate method
    with patch.object(assistant.llm_manager, 'generate', new_callable=AsyncMock) as mock_generate:
        mock_generate.return_value = "Salom! Qanday yordam bera olaman?"
        
        # Call the wake word handler
        await assistant._handle_wake_word()
        
        # Verify memory contains both user and assistant messages
        messages = assistant.memory.messages
        assert len(messages) >= 2
        assert any(msg['role'] == 'user' and msg['content'] == 'Salom Alisa' for msg in messages)
        assert any(msg['role'] == 'assistant' and msg['content'] == 'Salom! Qanday yordam bera olaman?' for msg in messages)


@pytest.mark.asyncio
async def test_process_text_none():
    """process_text handles None input gracefully."""
    reset_config()
    assistant = AlisaAssistant()
    
    response = await assistant.process_text(None)
    
    assert response == "Kechirasiz, javob bera olmadim."


@pytest.mark.asyncio
async def test_process_text_empty_string():
    """process_text handles empty string input gracefully."""
    reset_config()
    assistant = AlisaAssistant()
    
    response = await assistant.process_text("")
    
    assert response == "Kechirasiz, javob bera olmadim."


@pytest.mark.asyncio
async def test_process_text_non_string():
    """process_text handles non-string input gracefully."""
    reset_config()
    assistant = AlisaAssistant()
    
    response = await assistant.process_text(123)
    
    assert response == "Kechirasiz, javob bera olmadim."


@pytest.mark.asyncio
async def test_uzbek_system_prompt_used():
    """Verify that the canonical Uzbek system prompt is used in _think method."""
    reset_config()
    assistant = AlisaAssistant()
    
    # Mock the LLMManager to capture the system prompt
    with patch.object(assistant.llm_manager, 'generate', new_callable=AsyncMock) as mock_generate:
        mock_generate.return_value = "Test response"
        
        await assistant._think("Test input")
        
        # Verify that generate was called with the correct Uzbek system prompt
        mock_generate.assert_called_once()
        call_args = mock_generate.call_args
        assert call_args[1]['system_prompt'] == ALISA_SYSTEM_PROMPT_UZ
        
        # Verify the system prompt contains the expected Uzbek text
        assert "Sen Alisa — aqlli yordamchi" in ALISA_SYSTEM_PROMPT_UZ
        assert "o'zbek tilida gaplashasan" in ALISA_SYSTEM_PROMPT_UZ
        assert "Raspberry Pi da ishlaysan" in ALISA_SYSTEM_PROMPT_UZ
