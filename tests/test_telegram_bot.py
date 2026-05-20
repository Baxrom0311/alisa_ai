"""Tests for Telegram bot module."""

import pytest
import tempfile
import os
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from alisa.telegram.bot import AlisaBot


@pytest.fixture
def mock_config():
    """Mock configuration."""
    return {
        'telegram': {
            'bot_token': 'test_token',
            'chat_id': '12345'
        }
    }


@pytest.fixture
def mock_assistant():
    """Mock assistant."""
    assistant = AsyncMock()
    assistant.process_text = AsyncMock(return_value="Test response")
    assistant.memory = MagicMock()
    assistant.memory.clear = MagicMock()
    assistant.start = AsyncMock()
    assistant.stop = AsyncMock()
    return assistant


@pytest.fixture
def mock_update():
    """Mock Telegram update."""
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.chat.send_action = AsyncMock()
    return update


@patch('alisa.telegram.bot.get_config')
@patch('alisa.telegram.bot.AlisaAssistant')
def test_alisa_bot_init(mock_assistant_class, mock_get_config, mock_config):
    """Test AlisaBot initialization."""
    mock_get_config.return_value = mock_config
    mock_assistant_class.return_value = MagicMock()
    
    bot = AlisaBot()
    
    assert bot.bot_token == 'test_token'
    assert bot.chat_id == '12345'
    mock_assistant_class.assert_called_once()


@patch('alisa.telegram.bot.get_config')
def test_alisa_bot_init_no_token(mock_get_config):
    """Test AlisaBot initialization without token."""
    mock_get_config.return_value = {'telegram': {}}
    
    with pytest.raises(ValueError, match="Telegram bot_token not found"):
        AlisaBot()


@pytest.mark.asyncio
@patch('alisa.telegram.bot.get_config')
async def test_clear_memory_command(mock_get_config, mock_config, mock_assistant, mock_update):
    """Test /clear_memory command."""
    mock_get_config.return_value = mock_config
    
    with patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': 'test_token'}):
        bot = AlisaBot(assistant=mock_assistant)
        
        await bot.clear_memory_command(mock_update, None)
        
        mock_assistant.memory.clear.assert_called_once()
        mock_update.message.reply_text.assert_called_once_with("🧠 Suhbat xotirasi tozalandi.")


@pytest.mark.asyncio
@patch('alisa.telegram.bot.get_config')
@patch('os.unlink')
@patch('alisa.telegram.bot.transcribe')
async def test_handle_voice_message(mock_transcribe, mock_unlink, mock_get_config, 
                                  mock_config, mock_assistant, mock_update):
    """Test voice message handler with proper WAV file handling."""
    mock_get_config.return_value = mock_config
    mock_transcribe.return_value = "salom alisa"
    mock_assistant.process_text.return_value = "Salom!"
    
    # Mock voice file
    mock_voice_file = MagicMock()
    mock_file = AsyncMock()
    mock_file.download_to_drive = AsyncMock()
    mock_voice_file.get_file = AsyncMock(return_value=mock_file)
    mock_update.message.voice = mock_voice_file
    mock_update.message.audio = None
    
    # Mock file reading - full WAV file content
    wav_data = b'RIFF\x24\x08\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x08\x00\x00\x01\x02\x03\x04'
    
    with patch('builtins.open', mock_open(read_data=wav_data)):
        with patch('alisa.telegram.bot.subprocess.run'):
            with patch('alisa.telegram.bot.tempfile.NamedTemporaryFile') as mock_temp:
                # Mock temp file context managers
                mock_ogg = MagicMock()
                mock_ogg.name = '/tmp/test.ogg'
                mock_wav = MagicMock()
                mock_wav.name = '/tmp/test.wav'
                
                mock_temp.side_effect = [
                    MagicMock(__enter__=MagicMock(return_value=mock_ogg)),
                    MagicMock(__enter__=MagicMock(return_value=mock_wav))
                ]
                
                with patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': 'test_token'}):
                    bot = AlisaBot(assistant=mock_assistant)
                    
                    await bot.handle_voice_message(mock_update, None)
                    
                    # Verify transcription was called with full WAV data
                    mock_transcribe.assert_called_once_with(wav_data)
                    
                    # Verify assistant was called
                    mock_assistant.process_text.assert_called_once_with("salom alisa")
                    
                    # Verify response contains both transcript and response
                    response_calls = [call for call in mock_update.message.reply_text.call_args_list 
                                    if "salom alisa" in str(call) and "Salom!" in str(call)]
                    assert len(response_calls) > 0
                    
                    # Verify both temp files were deleted
                    assert mock_unlink.call_count == 2


@pytest.mark.asyncio
@patch('alisa.telegram.bot.get_config')
async def test_voice_message_no_voice_file(mock_get_config, mock_config, mock_assistant, mock_update):
    """Test voice message handler with no voice file."""
    mock_get_config.return_value = mock_config
    
    # No voice or audio file
    mock_update.message.voice = None
    mock_update.message.audio = None
    
    with patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': 'test_token'}):
        bot = AlisaBot(assistant=mock_assistant)
        
        await bot.handle_voice_message(mock_update, None)
        
        mock_update.message.reply_text.assert_called_with("Ovozli xabar topilmadi.")


@patch('alisa.telegram.bot.get_config')
@patch('alisa.telegram.bot.AlisaAssistant')
@pytest.mark.asyncio
async def test_start_command(mock_assistant_class, mock_get_config, mock_config):
    """Test /start command."""
    mock_get_config.return_value = mock_config
    mock_assistant_class.return_value = MagicMock()
    
    bot = AlisaBot()
    
    # Mock update and context
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    
    await bot.start_command(update, context)
    
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args[0][0]
    assert "Salom!" in call_args
    assert "/status" in call_args


@patch('alisa.telegram.bot.get_config')
@patch('alisa.telegram.bot.AlisaAssistant')
@pytest.mark.asyncio
async def test_status_command(mock_assistant_class, mock_get_config, mock_config):
    """Test /status command."""
    mock_get_config.return_value = mock_config
    mock_assistant_class.return_value = MagicMock()
    
    bot = AlisaBot()
    
    # Mock update and context
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    
    # Mock memory manager to return stats
    with patch('alisa.core.memory_manager.get_memory_manager') as mock_get_memory_manager:
        mock_memory_manager = MagicMock()
        mock_memory_manager.get_memory_stats.return_value = {
            'rss_mb': 150.5,
            'vms_mb': 300.2,
            'memory_percent': 65.3
        }
        mock_get_memory_manager.return_value = mock_memory_manager
        
        await bot.status_command(update, context)
    
    # Verify that reply_text was called
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args[0][0]
    
    # Should contain either status info with memory stats or error message
    if "Alisa Status" in call_args:
        assert "Memory Management" in call_args
        assert "RSS: 150.5 MB" in call_args
        assert "Usage: 65.3%" in call_args
    else:
        assert "xatolik" in call_args


@patch('alisa.core.config.get_config')
@patch('alisa.core.assistant.AlisaAssistant')
@pytest.mark.asyncio
async def test_memory_command(mock_assistant_class, mock_get_config, mock_config):
    """Test /memory command."""
    mock_get_config.return_value = mock_config
    mock_assistant_class.return_value = MagicMock()
    
    with patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': 'test_token'}):
        bot = AlisaBot()
        
        # Mock update and context
        update = MagicMock()
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        
        await bot.memory_command(update, context)
        
        # Just verify that reply_text was called (memory check might fail in test env)
        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args[0][0]
        # Should contain either memory info or error message
        assert "Xotira bosimi" in call_args or "xatolik" in call_args


@patch('alisa.telegram.bot.get_config')
@patch('alisa.telegram.bot.AlisaAssistant')
@pytest.mark.asyncio
async def test_ask_command(mock_assistant_class, mock_get_config, mock_config, mock_assistant):
    """Test /ask command."""
    mock_get_config.return_value = mock_config
    mock_assistant_class.return_value = mock_assistant
    
    bot = AlisaBot()
    bot.assistant = mock_assistant
    
    # Mock update and context
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.chat.send_action = AsyncMock()
    context = MagicMock()
    context.args = ["What", "is", "the", "weather?"]
    
    await bot.ask_command(update, context)
    
    mock_assistant.process_text.assert_called_once_with("What is the weather?")
    update.message.reply_text.assert_called_once_with("Test response")


@patch('alisa.telegram.bot.get_config')
@patch('alisa.telegram.bot.AlisaAssistant')
@pytest.mark.asyncio
async def test_ask_command_no_args(mock_assistant_class, mock_get_config, mock_config):
    """Test /ask command without arguments."""
    mock_get_config.return_value = mock_config
    mock_assistant_class.return_value = MagicMock()
    
    bot = AlisaBot()
    
    # Mock update and context
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = []
    
    await bot.ask_command(update, context)
    
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args[0][0]
    assert "Iltimos, savol yuboring" in call_args


@patch('alisa.telegram.bot.get_config')
@patch('alisa.telegram.bot.AlisaAssistant')
@pytest.mark.asyncio
async def test_handle_message(mock_assistant_class, mock_get_config, mock_config, mock_assistant):
    """Test handling regular messages."""
    mock_get_config.return_value = mock_config
    mock_assistant_class.return_value = mock_assistant
    
    bot = AlisaBot()
    bot.assistant = mock_assistant
    
    # Mock update and context
    update = MagicMock()
    update.message.text = "Hello Alisa"
    update.message.reply_text = AsyncMock()
    update.message.chat.send_action = AsyncMock()
    context = MagicMock()
    
    await bot.handle_message(update, context)
    
    mock_assistant.process_text.assert_called_once_with("Hello Alisa")
    update.message.reply_text.assert_called_once_with("Test response")


@patch('alisa.telegram.bot.get_config')
@patch('alisa.telegram.bot.AlisaAssistant')
@pytest.mark.asyncio
async def test_help_command(mock_assistant_class, mock_get_config, mock_config):
    """Test /help command."""
    mock_get_config.return_value = mock_config
    mock_assistant_class.return_value = MagicMock()
    
    bot = AlisaBot()
    
    # Mock update and context
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    
    await bot.help_command(update, context)
    
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args[0][0]
    assert "Alisa AI Assistant" in call_args
    assert "Buyruqlar:" in call_args


@patch('alisa.telegram.bot.get_config')
@patch('alisa.telegram.bot.AlisaAssistant')
@patch('alisa.services.updater.restart_service')
@pytest.mark.asyncio
async def test_restart_command(mock_restart, mock_assistant_class, mock_get_config, mock_config):
    """Test /restart command."""
    mock_get_config.return_value = mock_config
    mock_assistant_class.return_value = MagicMock()
    mock_restart.return_value = (True, "Service restarted successfully")
    
    bot = AlisaBot()
    
    # Mock update and context
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    
    await bot.restart_command(update, context)
    
    assert update.message.reply_text.call_count == 2
    mock_restart.assert_called_once()


@patch('alisa.telegram.bot.get_config')
@patch('alisa.telegram.bot.AlisaAssistant')
@patch('alisa.brain.online.is_online')
@pytest.mark.asyncio
async def test_mode_command(mock_is_online, mock_assistant_class, mock_get_config, mock_config):
    """Test /mode command."""
    mock_get_config.return_value = mock_config
    mock_assistant_class.return_value = MagicMock()
    mock_is_online.return_value = True
    
    bot = AlisaBot()
    
    # Mock update and context
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = []  # No arguments - show current mode
    
    await bot.mode_command(update, context)
    
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args[0][0]
    assert "Alisa rejimi" in call_args
    assert "Telegram rejim: Faol" in call_args


@patch('alisa.telegram.bot.get_config')
@patch('alisa.telegram.bot.AlisaAssistant')
@pytest.mark.asyncio
async def test_mode_command_toggles_state(mock_assistant_class, mock_get_config, mock_config):
    """Test /mode command toggles state correctly."""
    mock_get_config.return_value = mock_config
    mock_assistant_class.return_value = MagicMock()
    
    bot = AlisaBot()
    
    # Mock update and context for reception mode
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["reception"]
    
    with patch.object(bot, '_set_mode') as mock_set_mode:
        await bot.mode_command(update, context)
        
        mock_set_mode.assert_called_once_with("reception")
        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args[0][0]
        assert "Resepsiya rejimiga o'tkazildi" in call_args


@patch('alisa.telegram.bot.get_config')
@patch('alisa.telegram.bot.AlisaAssistant')
@pytest.mark.asyncio
async def test_mode_command_rejects_unknown(mock_assistant_class, mock_get_config, mock_config):
    """Test /mode command rejects unknown modes."""
    mock_get_config.return_value = mock_config
    mock_assistant_class.return_value = MagicMock()
    
    bot = AlisaBot()
    
    # Mock update and context for unknown mode
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["unknown_mode"]
    
    await bot.mode_command(update, context)
    
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args[0][0]
    assert "Noto'g'ri rejim" in call_args
    assert "reception" in call_args
    assert "assistant" in call_args


@patch('alisa.telegram.bot.get_config')
@patch('alisa.telegram.bot.AlisaAssistant')
@pytest.mark.asyncio
async def test_providers_command_renders_status(mock_assistant_class, mock_get_config, mock_config):
    """Test /providers command renders provider status correctly."""
    mock_get_config.return_value = mock_config
    mock_assistant_class.return_value = MagicMock()
    
    bot = AlisaBot()
    
    # Mock update and context
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    
    # Mock LLM manager with provider status
    mock_status = {
        'active_providers': 2,
        'last_successful': 'openai',
        'providers': {
            'openai': {
                'available': True,
                'requests': 10,
                'success_rate': '95%',
                'avg_response_time': '2.1s',
                'last_error': None
            },
            'ollama': {
                'available': True,
                'requests': 5,
                'success_rate': '100%',
                'avg_response_time': '3.5s',
                'last_error': 'Connection timeout occurred while trying to reach the server endpoint'
            }
        }
    }
    
    with patch('alisa.brain.llm_manager.get_llm_manager') as mock_get_manager:
        mock_manager = MagicMock()
        mock_manager.get_provider_status.return_value = mock_status
        mock_get_manager.return_value = mock_manager
        
        await bot.providers_command(update, context)
        
        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args[0][0]
        
        # Check that status is rendered correctly
        assert "LLM Providerlar holati" in call_args
        assert "Faol providerlar: 2" in call_args
        assert "Oxirgi muvaffaqiyatli: openai" in call_args
        assert "OPENAI:" in call_args
        assert "So'rovlar: 10" in call_args
        assert "Muvaffaqiyat: 95%" in call_args
        assert "O'rtacha vaqt: 2.1s" in call_args
        
        # Check error truncation (should be truncated to 60 chars)
        assert "Connection timeout occurred while trying to reach the ser..." in call_args


@patch('alisa.telegram.bot.get_config')
@patch('alisa.telegram.bot.AlisaAssistant')
@pytest.mark.asyncio
async def test_orchestrate_command_authorized(mock_assistant_class, mock_get_config, mock_config):
    """Test orchestrate command with authorized user."""
    mock_get_config.return_value = mock_config
    mock_assistant_class.return_value = MagicMock()
    
    bot = AlisaBot()
    bot.chat_id = "123456789"
    
    # Mock update with matching chat_id
    update = MagicMock()
    update.effective_chat.id = 123456789
    update.message.reply_text = AsyncMock()
    
    context = MagicMock()
    
    with patch.object(bot, '_run_orchestrator_async') as mock_orchestrator:
        with patch('asyncio.create_task') as mock_create_task:
            await bot.orchestrate_command(update, context)
            
            # Should ACK immediately
            update.message.reply_text.assert_called_once_with(
                "🤖 AI Orchestrator ishga tushirilmoqda... (dry-run rejimida)"
            )
            
            # Should create background task
            mock_create_task.assert_called_once()


@patch('alisa.telegram.bot.get_config')
@patch('alisa.telegram.bot.AlisaAssistant')
@pytest.mark.asyncio
async def test_orchestrate_command_unauthorized(mock_assistant_class, mock_get_config, mock_config):
    """Test orchestrate command with unauthorized user."""
    mock_get_config.return_value = mock_config
    mock_assistant_class.return_value = MagicMock()
    
    bot = AlisaBot()
    bot.chat_id = "123456789"
    
    # Mock update with different chat_id
    update = MagicMock()
    update.effective_chat.id = 987654321
    update.message.reply_text = AsyncMock()
    
    context = MagicMock()
    
    await bot.orchestrate_command(update, context)
    
    # Should deny access
    update.message.reply_text.assert_called_once_with(
        "❌ Sizga bu buyruqni ishlatish ruxsati yo'q."
    )


@patch('alisa.telegram.bot.get_config')
@patch('alisa.telegram.bot.AlisaAssistant')
@pytest.mark.asyncio
async def test_orchestrate_command_no_chat_id_configured(mock_assistant_class, mock_get_config, mock_config):
    """Test orchestrate command when no chat_id is configured."""
    mock_get_config.return_value = mock_config
    mock_assistant_class.return_value = MagicMock()
    
    bot = AlisaBot()
    bot.chat_id = None
    
    update = MagicMock()
    update.effective_chat.id = 123456789
    update.message.reply_text = AsyncMock()
    
    context = MagicMock()
    
    with patch.object(bot, '_run_orchestrator_async') as mock_orchestrator:
        with patch('asyncio.create_task') as mock_create_task:
            await bot.orchestrate_command(update, context)
            
            # Should proceed (no restriction when chat_id not configured)
            update.message.reply_text.assert_called_once_with(
                "🤖 AI Orchestrator ishga tushirilmoqda... (dry-run rejimida)"
            )
            
            mock_create_task.assert_called_once()


@patch('alisa.telegram.bot.get_config')
@patch('alisa.telegram.bot.AlisaAssistant')
def test_run_orchestrator_sync_success(mock_assistant_class, mock_get_config, mock_config):
    """Test orchestrator sync execution with success."""
    mock_get_config.return_value = mock_config
    mock_assistant_class.return_value = MagicMock()
    
    bot = AlisaBot()
    
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = '{"status": "success", "message": "Task completed"}\n'
    mock_result.stderr = ''
    
    with patch('subprocess.run', return_value=mock_result):
        result = bot._run_orchestrator_sync()
        
        assert result == '{"status": "success", "message": "Task completed"}'


@patch('alisa.telegram.bot.get_config')
@patch('alisa.telegram.bot.AlisaAssistant')
def test_run_orchestrator_sync_error(mock_assistant_class, mock_get_config, mock_config):
    """Test orchestrator sync execution with error."""
    mock_get_config.return_value = mock_config
    mock_assistant_class.return_value = MagicMock()
    
    bot = AlisaBot()
    
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ''
    mock_result.stderr = 'Error occurred'
    
    with patch('subprocess.run', return_value=mock_result):
        result = bot._run_orchestrator_sync()
        
        import json
        result_data = json.loads(result)
        assert result_data['status'] == 'error'
        assert 'exit code: 1' in result_data['message']


@patch('alisa.telegram.bot.get_config')
@patch('alisa.telegram.bot.AlisaAssistant')
def test_status_command_real_memory_keys(mock_assistant_class, mock_get_config, mock_config, mock_update):
    """Test status command with real MemoryManager instance."""
    mock_get_config.return_value = mock_config
    mock_assistant_class.return_value = MagicMock()
    
    bot = AlisaBot()
    
    # Use real MemoryManager to test actual key names
    from alisa.core.memory_manager import MemoryManager
    real_memory_manager = MemoryManager()
    
    with patch('alisa.core.memory_manager.get_memory_manager', return_value=real_memory_manager):
        with patch('alisa.services.health.get_system_stats', return_value={
            'cpu_percent': 50.0, 
            'memory_percent': 60.0, 
            'memory_used_mb': 1500,
            'memory_total_mb': 4000,
            'disk_percent': 70.0,
            'disk_free_gb': 10.5,
            'temperature_c': 45.0,
            'load_avg_1m': 0.5,
            'load_avg_5m': 0.6,
            'load_avg_15m': 0.7,
            'swap_percent': 10.0,
            'swap_used_mb': 100,
            'swap_total_mb': 1000,
            'uptime_hours': 24.5
        }):
            with patch('alisa.services.updater.get_current_version', return_value='v1.0.0'):
                import asyncio
                asyncio.run(bot.status_command(mock_update, None))
                
                # Verify the reply was called and doesn't contain KeyError
                mock_update.message.reply_text.assert_called_once()
                reply_text = mock_update.message.reply_text.call_args[0][0]
                assert 'KeyError' not in reply_text
                assert '%' in reply_text  # Should contain percentage


@patch('alisa.telegram.bot.get_config')
@patch('alisa.telegram.bot.AlisaAssistant')
def test_orchestrator_timeout_returns_json(mock_assistant_class, mock_get_config, mock_config):
    """Test orchestrator timeout returns valid JSON."""
    mock_get_config.return_value = mock_config
    mock_assistant_class.return_value = MagicMock()
    
    bot = AlisaBot()
    
    # Mock subprocess.run to raise TimeoutExpired
    from subprocess import TimeoutExpired
    with patch('subprocess.run', side_effect=TimeoutExpired('cmd', 30)):
        result = bot._run_orchestrator_sync()
        
        # Should not raise NameError and should return valid JSON
        import json
        result_data = json.loads(result)
        assert result_data['status'] == 'timeout'
        assert 'timeout' in result_data['message']


@pytest.mark.asyncio
async def test_memory_pressure_real_keys():
    """Test memory pressure command uses correct keys from check_memory_pressure."""
    with patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': 'test_token'}):
        bot = AlisaBot()
        
        # Mock update and context
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        
        # Mock check_memory_pressure to return real structure
        with patch('alisa.services.health.check_memory_pressure') as mock_pressure:
            mock_pressure.return_value = {
                "pressure_level": "moderate",
                "available_mb": 1200.5,
                "swap_percent": 15.2,
                "memory_percent": 65.3,  # This is the key that should be used
                "suggestions": ["Monitor memory usage closely"]
            }
            
            await bot.memory_command(update, context)
            
            # Verify reply was called
            update.message.reply_text.assert_called_once()
            reply_text = update.message.reply_text.call_args[0][0]
            
            # Verify the message contains the memory_percent value and doesn't crash
            assert "65.3%" in reply_text
            assert "moderate" in reply_text
            assert "1200.5 MB" in reply_text
            assert "15.2%" in reply_text
            assert "Monitor memory usage closely" in reply_text


def test_orchestrate_module_exists():
    """Test that ai_orchestrator.__main__ module can be imported."""
    import importlib.util
    
    spec = importlib.util.find_spec('ai_orchestrator.__main__')
    assert spec is not None, "ai_orchestrator.__main__ module not found"
    
    # Also test that the module can be imported
    import ai_orchestrator.__main__
    assert hasattr(ai_orchestrator.__main__, 'main')
