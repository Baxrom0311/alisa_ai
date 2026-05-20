"""Test telegram notifier environment variable precedence."""

import os
import pytest
from unittest.mock import patch
from ai_orchestrator.telegram_notifier import TelegramNotifier


def test_telegram_notifier_env_var_precedence():
    """Test that environment variables take precedence over constructor args."""
    # Test env vars override constructor args
    with patch.dict(os.environ, {
        'TELEGRAM_BOT_TOKEN': 'env_token_123',
        'TELEGRAM_CHAT_ID': 'env_chat_456'
    }):
        notifier = TelegramNotifier(
            bot_token='constructor_token',
            chat_id='constructor_chat',
            enabled=True
        )
        
        assert notifier.bot_token == 'env_token_123'
        assert notifier.chat_id == 'env_chat_456'
        assert notifier.enabled is True


def test_telegram_notifier_fallback_to_constructor():
    """Test fallback to constructor args when env vars not set."""
    with patch.dict(os.environ, {}, clear=True):
        notifier = TelegramNotifier(
            bot_token='constructor_token',
            chat_id='constructor_chat',
            enabled=True
        )
        
        assert notifier.bot_token == 'constructor_token'
        assert notifier.chat_id == 'constructor_chat'
        assert notifier.enabled is True


def test_telegram_notifier_disabled_when_missing_credentials():
    """Test that notifier is disabled when credentials are missing."""
    with patch.dict(os.environ, {}, clear=True):
        notifier = TelegramNotifier(enabled=True)
        
        assert notifier.bot_token == ''
        assert notifier.chat_id == ''
        assert notifier.enabled is False
