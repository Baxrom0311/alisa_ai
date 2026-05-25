"""Integration tests for Alisa AI Assistant."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from alisa.core.assistant import AlisaAssistant
from alisa.telegram.bot import AlisaBot
from alisa.reception.greeter import ReceptionGreeter


class TestIntegration:
    """Integration tests for main Alisa components."""
    
    @pytest.mark.asyncio
    async def test_assistant_initialization(self):
        """Test that assistant can be initialized properly."""
        assistant = AlisaAssistant()
        
        assert assistant is not None
        assert assistant.config is not None
        assert assistant.memory is not None
        assert assistant.memory_manager is not None
        assert assistant.profiler is not None
        assert assistant.is_running is False
    
    @pytest.mark.asyncio
    async def test_telegram_bot_initialization(self):
        """Test that Telegram bot can be initialized with assistant."""
        assistant = AlisaAssistant()
        greeter = ReceptionGreeter()
        
        with patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': 'test_token'}):
            bot = AlisaBot(assistant=assistant, greeter=greeter)
            
            assert bot is not None
            assert bot.assistant is assistant
            assert bot.greeter is greeter
    
    @pytest.mark.asyncio
    async def test_reception_greeter_initialization(self):
        """Test that reception greeter can be initialized."""
        async def mock_notifier(message):
            pass
        
        greeter = ReceptionGreeter(telegram_notifier=mock_notifier)
        
        assert greeter is not None
        assert greeter.telegram_notifier is mock_notifier
    
    @pytest.mark.asyncio
    async def test_assistant_think_fallback(self):
        """Test that assistant handles no providers gracefully."""
        # Mock config with no providers to test the "no providers" case
        mock_config = {
            "llm": {
                "timeout_sec": 5,
                "local_timeout_sec": 10,
                "providers": []  # No providers
            }
        }
        
        with patch('alisa.brain.llm_manager.get_config', return_value=mock_config):
            assistant = AlisaAssistant()
            
            # Should fall back to intent detection or "no providers" message
            result = await assistant._think("Kvant fizikasi nima")
            
            assert result is not None
            assert isinstance(result, str)
            assert len(result) > 0
            # Should contain the fallback message
            assert "LLM mavjud emas" in result
    
    @pytest.mark.asyncio
    async def test_reception_guest_handling_integration(self):
        """Test reception mode guest handling integration."""
        notifications = []
        
        async def mock_notifier(message):
            notifications.append(message)
        
        greeter = ReceptionGreeter(telegram_notifier=mock_notifier)
        
        # Handle a guest - this should work without external dependencies
        await greeter._handle_guest()
        
        # Verify notification was sent (this is the key integration point)
        assert len(notifications) == 1
        assert "Mehmon keldi" in notifications[0]
        
        # Verify guest was logged
        guest_log = greeter.get_guest_log()
        assert len(guest_log) == 1
        assert guest_log[0]['greeted'] is True
    
    @pytest.mark.asyncio
    async def test_memory_system_basic(self):
        """Test that memory system can store and retrieve messages."""
        assistant = AlisaAssistant()
        
        # Add a message to memory
        assistant.memory.add_message("user", "Test message")
        
        # Verify it was stored by checking the messages property
        messages = assistant.memory.messages
        assert len(messages) > 0
        assert any(msg["content"] == "Test message" for msg in messages)
    
    def test_config_integration(self):
        """Test that all components can access configuration."""
        from alisa.core.config import get_config
        
        config = get_config()
        
        # Verify essential config sections exist (using actual config structure)
        assert 'audio' in config
        assert 'ollama' in config
        assert 'piper' in config  # Use 'piper' instead of 'tts'
        
        # Test that components can initialize with config
        assistant = AlisaAssistant()
        assert assistant.config == config
        
        greeter = ReceptionGreeter()
        # Greeter should be able to initialize without errors
        assert greeter is not None
    
    @pytest.mark.asyncio
    async def test_component_error_handling(self):
        """Test that components handle errors gracefully."""
        assistant = AlisaAssistant()
        
        # Test with empty input
        result = await assistant._think("")
        assert result is not None
        assert isinstance(result, str)
        
        # Test with very long input
        long_input = "A" * 10000
        result = await assistant._think(long_input)
        assert result is not None
        assert isinstance(result, str)
    
    def test_system_validation_integration(self):
        """Test that system validation works."""
        from alisa.core.validator import validate_system, get_system_info
        
        # Should not crash
        is_valid, issues = validate_system()
        assert isinstance(is_valid, bool)
        assert isinstance(issues, list)
        
        # System info should be available
        system_info = get_system_info()
        assert isinstance(system_info, dict)
        assert 'os' in system_info  # Use 'os' instead of 'platform'
