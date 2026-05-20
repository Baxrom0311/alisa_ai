"""Tests for main orchestrator."""

import asyncio
import pytest
from unittest.mock import Mock, patch, AsyncMock
import os
from main import AlisaOrchestrator


class TestAlisaOrchestrator:
    """Test the main orchestrator functionality."""
    
    def test_single_assistant_instance(self):
        """Test that exactly one AlisaAssistant instance exists across orchestrator + bot."""
        orchestrator = AlisaOrchestrator()
        
        # Orchestrator should have one assistant
        assert orchestrator.assistant is not None
        original_assistant = orchestrator.assistant
        
        # Mock environment for telegram bot
        with patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': 'test_token'}):
            # Create telegram bot with shared instances
            from alisa.telegram.bot import AlisaBot
            
            # Create notifier function
            async def mock_notifier(message):
                pass
            
            # Create reception greeter
            from alisa.reception.greeter import ReceptionGreeter
            reception_greeter = ReceptionGreeter(telegram_notifier=mock_notifier)
            
            # Create bot with shared instances
            bot = AlisaBot(assistant=orchestrator.assistant, greeter=reception_greeter)
            
            # Verify same instance is used
            assert bot.assistant is original_assistant
            assert id(bot.assistant) == id(original_assistant)
    
    def test_orchestrator_initialization(self):
        """Test orchestrator initializes with required components."""
        orchestrator = AlisaOrchestrator()
        
        # Should have assistant instance
        assert orchestrator.assistant is not None
        
        # Other components should be None initially
        assert orchestrator.telegram_bot is None
        assert orchestrator.reception_greeter is None
        assert orchestrator.running_tasks == []
    
    @pytest.mark.asyncio
    async def test_telegram_mode_without_token(self):
        """Test telegram mode fails gracefully without token."""
        orchestrator = AlisaOrchestrator()
        
        # Ensure no token in environment
        with patch.dict(os.environ, {}, clear=True):
            task = await orchestrator.start_telegram_mode()
            assert task is None
            assert orchestrator.telegram_bot is None
    
    @pytest.mark.asyncio
    async def test_telegram_mode_with_token(self):
        """Test telegram mode starts with valid token."""
        orchestrator = AlisaOrchestrator()
        
        with patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': 'test_token'}):
            with patch('alisa.telegram.bot.AlisaBot.start_bot', new_callable=AsyncMock) as mock_start:
                mock_start.return_value = None
                
                task = await orchestrator.start_telegram_mode()
                
                # Should create telegram bot with shared instances
                assert orchestrator.telegram_bot is not None
                assert orchestrator.telegram_bot.assistant is orchestrator.assistant
                assert task is not None
    
    @pytest.mark.asyncio
    async def test_voice_mode_start(self):
        """Test voice mode starts correctly."""
        orchestrator = AlisaOrchestrator()
        
        with patch.object(orchestrator.assistant, 'start', new_callable=AsyncMock) as mock_start:
            mock_start.return_value = None
            
            task = await orchestrator.start_voice_mode()
            
            assert task is not None
            assert len(orchestrator.running_tasks) == 1
    
    @pytest.mark.asyncio
    async def test_reception_mode_start(self):
        """Test reception mode starts correctly."""
        orchestrator = AlisaOrchestrator()
        
        with patch('alisa.reception.greeter.ReceptionGreeter.start_reception_mode', new_callable=AsyncMock) as mock_start:
            mock_start.return_value = None
            
            task = await orchestrator.start_reception_mode()
            
            assert task is not None
            assert orchestrator.reception_greeter is not None
            assert len(orchestrator.running_tasks) == 1
    
    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Test graceful shutdown."""
        orchestrator = AlisaOrchestrator()
        
        # Mock components
        orchestrator.assistant.stop = Mock()
        
        mock_greeter = Mock()
        mock_greeter.stop_reception_mode = Mock()
        orchestrator.reception_greeter = mock_greeter
        
        mock_bot = Mock()
        mock_bot.stop_bot = AsyncMock()
        orchestrator.telegram_bot = mock_bot
        
        # Add mock task (create a proper asyncio task)
        async def dummy_task():
            await asyncio.sleep(0.1)
        
        task = asyncio.create_task(dummy_task())
        orchestrator.running_tasks = [task]
        
        await orchestrator.shutdown()
        
        # Verify all components were stopped
        orchestrator.assistant.stop.assert_called_once()
        mock_greeter.stop_reception_mode.assert_called_once()
        mock_bot.stop_bot.assert_called_once()
        
        # Task should be cancelled
        assert task.cancelled() or task.done()
