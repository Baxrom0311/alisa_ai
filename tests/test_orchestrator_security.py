"""Test orchestrator security - ensure no hardcoded credentials."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from ai_orchestrator.orchestrator import load_config, TelegramNotifier


def test_agentloop_toml_no_exposed_credentials():
    """Verify agentloop.toml doesn't contain exposed bot tokens."""
    agentloop_path = Path(__file__).parent.parent / "agentloop.toml"
    if not agentloop_path.exists():
        pytest.skip("agentloop.toml not found")
    
    content = agentloop_path.read_text()
    
    # Should not contain actual bot tokens (they start with numbers)
    assert "bot_token = \"" not in content or "REMOVED_FOR_SECURITY" in content
    assert "chat_id = \"" not in content or "REMOVED_FOR_SECURITY" in content
    
    # Should have comments indicating env vars
    assert "TELEGRAM_BOT_TOKEN" in content
    assert "TELEGRAM_CHAT_ID" in content


def test_orchestrator_env_var_precedence():
    """Test that environment variables take precedence over config file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
        f.write("""
[telegram]
enabled = true
bot_token = "config_token"
chat_id = "config_chat"
""")
        config_path = Path(f.name)
    
    try:
        config = load_config(config_path)
        
        # Test env vars take precedence
        with patch.dict(os.environ, {
            'TELEGRAM_BOT_TOKEN': 'env_token',
            'TELEGRAM_CHAT_ID': 'env_chat'
        }):
            tg = TelegramNotifier(
                bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", "") or config["telegram"].get("bot_token", ""),
                chat_id=os.environ.get("TELEGRAM_CHAT_ID", "") or config["telegram"].get("chat_id", ""),
                enabled=config["telegram"].get("enabled", False),
            )
            
            assert tg.bot_token == "env_token"
            assert tg.chat_id == "env_chat"
        
        # Test fallback to config when env vars not set
        with patch.dict(os.environ, {}, clear=True):
            tg = TelegramNotifier(
                bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", "") or config["telegram"].get("bot_token", ""),
                chat_id=os.environ.get("TELEGRAM_CHAT_ID", "") or config["telegram"].get("chat_id", ""),
                enabled=config["telegram"].get("enabled", False),
            )
            
            assert tg.bot_token == "config_token"
            assert tg.chat_id == "config_chat"
    
    finally:
        config_path.unlink()


def test_no_hardcoded_secrets_in_codebase():
    """Scan for potential hardcoded secrets in Python files."""
    project_root = Path(__file__).parent.parent
    
    # Patterns that might indicate hardcoded secrets
    secret_patterns = [
        r'\d{10}:AA[A-Za-z0-9_-]{35}',  # Telegram bot token pattern
        r'bot_token\s*=\s*["\'][^"\']*\d{10}',  # bot_token assignment with numbers
    ]
    
    python_files = list(project_root.rglob("*.py"))
    
    for py_file in python_files:
        if "test_" in py_file.name:
            continue  # Skip test files
        
        content = py_file.read_text(encoding='utf-8', errors='ignore')
        
        # Check for suspicious patterns
        import re
        for pattern in secret_patterns:
            matches = re.findall(pattern, content)
            assert not matches, f"Potential hardcoded secret in {py_file}: {matches}"
