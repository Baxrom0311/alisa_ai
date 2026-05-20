"""Tests for alisa.core.config module."""

import os
import tempfile
import yaml
from pathlib import Path
from unittest.mock import patch

from alisa.core.config import get_config, reset_config


def test_defaults_when_no_file():
    """Config returns defaults when file doesn't exist."""
    reset_config()
    cfg = get_config(config_path="/nonexistent/path.yaml")
    assert "whisper" in cfg
    assert "piper" in cfg
    assert "ollama" in cfg
    assert "audio" in cfg
    assert cfg["ollama"]["model"] == "qwen2.5:3b"
    assert cfg["audio"]["sample_rate"] == 16000


def test_load_from_yaml():
    """Config loads values from YAML file."""
    reset_config()
    content = "ollama:\n  model: phi-3-mini\n  timeout: 60\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(content)
        f.flush()
        cfg = get_config(config_path=f.name)
    Path(f.name).unlink()
    assert cfg["ollama"]["model"] == "phi-3-mini"
    assert cfg["ollama"]["timeout"] == 60
    # Defaults preserved for unset keys
    assert cfg["ollama"]["url"] == "http://localhost:11434"
    assert cfg["whisper"]["binary"] == "/usr/local/bin/whisper-cli"


def test_singleton_caching():
    """get_config() returns cached instance on subsequent calls."""
    reset_config()
    cfg1 = get_config(config_path="/nonexistent.yaml")
    # Without config_path, returns cached
    cfg2 = get_config()
    assert cfg1 is cfg2


def test_invalid_yaml():
    """Config handles invalid YAML gracefully."""
    reset_config()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(": : : invalid yaml [[[")
        f.flush()
        cfg = get_config(config_path=f.name)
    Path(f.name).unlink()
    # Should fall back to defaults
    assert cfg["ollama"]["model"] == "qwen2.5:3b"


def test_openai_api_key_env_precedence():
    """Test OPENAI_API_KEY env var precedence over config file."""
    # Create a temporary config file with openai settings
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump({
            "openai": {
                "api_key": "config_key",
                "base_url": "https://api.openai.com/v1"
            }
        }, f)
        temp_config_path = f.name
    
    try:
        # Test env var precedence
        with patch.dict(os.environ, {"OPENAI_API_KEY": "env_key"}):
            reset_config()
            config = get_config(temp_config_path)
            assert config["openai"]["api_key"] == "env_key"
            assert config["openai"]["base_url"] == "https://api.openai.com/v1"  # From config
        
        # Test fallback to config when no env var
        with patch.dict(os.environ, {}, clear=True):
            reset_config()  # Clear cache
            config = get_config(temp_config_path)
            assert config["openai"]["api_key"] == "config_key"
            assert config["openai"]["base_url"] == "https://api.openai.com/v1"
        
        # Test default when neither env nor config
        reset_config()
        config = get_config("nonexistent.yaml")
        assert config["openai"]["api_key"] is None
        assert config["openai"]["base_url"] is None
        
    finally:
        os.unlink(temp_config_path)
