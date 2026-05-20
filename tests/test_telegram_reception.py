"""Integration tests for Telegram bot with reception mode."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from telegram import Update, Message, Chat, User
from alisa.telegram.bot import AlisaBot


class TestTelegramBotReception:
    """Test Telegram bot reception mode integration."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Mock the config to return a test token
        with patch('alisa.telegram.bot.get_config') as mock_config:
            mock_config.return_value = {
                'telegram': {
                    'bot_token': 'test_token',
                    'chat_id': None
                }
            }
            self.bot = AlisaBot()
    
    def teardown_method(self):
        """Clean up test fixtures."""
        # Stop reception mode to prevent async warnings
        if hasattr(self.bot, 'greeter') and hasattr(self.bot.greeter, 'is_active'):
            self.bot.greeter.stop_reception_mode()
    
    def _create_mock_update(self, text: str, chat_id: int = 123) -> Update:
        """Create a mock Telegram update."""
        user = Mock(spec=User)
        user.id = 456
        user.first_name = "Test"
        
        chat = Mock(spec=Chat)
        chat.id = chat_id
        chat.send_action = AsyncMock()
        
        message = Mock(spec=Message)
        message.text = text
        message.chat = chat
        message.reply_text = AsyncMock()
        
        update = Mock(spec=Update)
        update.message = message
        
        return update
    
    @pytest.mark.asyncio
    async def test_reception_start_command(self):
        """Test /reception_start command."""
        update = self._create_mock_update("/reception_start")
        context = Mock()
        
        # Mock greeter
        self.bot.greeter.is_active = False
        
        with patch('asyncio.create_task') as mock_task:
            await self.bot.reception_start_command(update, context)
        
        # Should create background task
        mock_task.assert_called_once()
        
        # Should send confirmation message
        update.message.reply_text.assert_called_once()
        reply_text = update.message.reply_text.call_args[0][0]
        assert "Resepsiya rejimi boshlandi" in reply_text
    
    @pytest.mark.asyncio
    async def test_reception_start_already_active(self):
        """Test /reception_start when already active."""
        update = self._create_mock_update("/reception_start")
        context = Mock()
        
        # Mock greeter as already active
        self.bot.greeter.is_active = True
        
        await self.bot.reception_start_command(update, context)
        
        # Should send already active message
        update.message.reply_text.assert_called_once()
        reply_text = update.message.reply_text.call_args[0][0]
        assert "allaqachon faol" in reply_text
    
    @pytest.mark.asyncio
    async def test_reception_stop_command(self):
        """Test /reception_stop command."""
        update = self._create_mock_update("/reception_stop")
        context = Mock()
        
        # Mock greeter as active
        self.bot.greeter.is_active = True
        
        await self.bot.reception_stop_command(update, context)
        
        # Should send confirmation message
        update.message.reply_text.assert_called_once()
        reply_text = update.message.reply_text.call_args[0][0]
        assert "to'xtatildi" in reply_text
    
    @pytest.mark.asyncio
    async def test_reception_stop_not_active(self):
        """Test /reception_stop when not active."""
        update = self._create_mock_update("/reception_stop")
        context = Mock()
        
        # Mock greeter as not active
        self.bot.greeter.is_active = False
        
        await self.bot.reception_stop_command(update, context)
        
        # Should send not active message
        update.message.reply_text.assert_called_once()
        reply_text = update.message.reply_text.call_args[0][0]
        assert "faol emas" in reply_text
    
    @pytest.mark.asyncio
    async def test_guests_command_no_guests(self):
        """Test /guests command with no guests."""
        update = self._create_mock_update("/guests")
        context = Mock()
        
        # Mock empty guest log
        self.bot.greeter.get_guest_log = Mock(return_value=[])
        
        await self.bot.guests_command(update, context)
        
        # Should send no guests message
        update.message.reply_text.assert_called_once()
        reply_text = update.message.reply_text.call_args[0][0]
        assert "mehmonlar kelmagan" in reply_text
    
    @pytest.mark.asyncio
    async def test_guests_command_with_guests(self):
        """Test /guests command with guest log."""
        update = self._create_mock_update("/guests")
        context = Mock()
        
        # Mock guest log with entries
        guest_log = [
            {"time": "2024-01-01 10:00:00", "greeted": True},
            {"time": "2024-01-01 11:30:00", "greeted": True}
        ]
        self.bot.greeter.get_guest_log = Mock(return_value=guest_log)
        
        await self.bot.guests_command(update, context)
        
        # Should send guest list
        update.message.reply_text.assert_called_once()
        reply_text = update.message.reply_text.call_args[0][0]
        assert "Bugungi mehmonlar" in reply_text
        assert "10:00:00" in reply_text
        assert "11:30:00" in reply_text
    
    @pytest.mark.asyncio
    async def test_send_notification(self):
        """Test sending notification."""
        # Mock app and bot
        self.bot.app = Mock()
        self.bot.app.bot = Mock()
        self.bot.app.bot.send_message = AsyncMock()
        self.bot.chat_id = 123
        
        await self.bot._send_notification("Test notification")
        
        # Should send message to configured chat
        self.bot.app.bot.send_message.assert_called_once_with(
            chat_id=123, 
            text="Test notification"
        )
    
    @pytest.mark.asyncio
    async def test_send_notification_no_chat_id(self):
        """Test sending notification without chat ID."""
        self.bot.app = Mock()
        self.bot.chat_id = None
        
        # Should not raise exception
        await self.bot._send_notification("Test notification")
