"""Configuration loader for Alisa AI Assistant."""

import os
from pathlib import Path

import structlog
import yaml

logger = structlog.get_logger()

_DEFAULTS = {
    "language": "uz",
    "wake_word": "alisa",
    "llm": {
        "timeout_sec": 5,
        "local_timeout_sec": 10,
        "providers": [
            {
                "name": "openai",
                "api_key": "",
                "model": "gpt-4o-mini",
                "base_url": "https://api.openai.com/v1"
            },
            {
                "name": "gemini", 
                "api_key": "",
                "model": "gemini-2.0-flash"
            },
            {
                "name": "deepseek",
                "api_key": "",
                "model": "deepseek-chat", 
                "base_url": "https://api.deepseek.com/v1"
            },
            {
                "name": "grok",
                "api_key": "",
                "model": "grok-2",
                "base_url": "https://api.x.ai/v1"
            },
            {
                "name": "claude",
                "api_key": "",
                "model": "claude-sonnet-4-20250514"
            },
            {
                "name": "ollama",
                "model": "qwen2.5:3b",
                "base_url": "http://localhost:11434"
            }
        ]
    },
    "whisper": {
        "binary": "/usr/local/bin/whisper-cli",
        "model": "/opt/alisa/models/ggml-base.bin",
        "language": "uz",
    },
    "piper": {
        "binary": "/usr/local/bin/piper",
        "model": "/opt/alisa/models/uz_UZ-doniyorbek-medium.onnx",
        "output_dir": "/tmp/alisa_tts",
    },
    "ollama": {
        "url": "http://localhost:11434",
        "model": "qwen2.5:3b",
        "timeout": 30,
    },
    "audio": {
        "sample_rate": 16000,
        "channels": 1,
        "input_device": None,
        "output_device": None,
    },
    "wake_word": {
        "keyword": "alisa",
        "sensitivity": 0.05,
        "confirmation_cooldown_sec": 5.0,
        "allow_proxy_model": False,  # Prefer energy-gated when keyword='alisa' and model='alexa'
    },
    "telegram": {
        "bot_token": None,
        "chat_id": None,
    },
    "reception": {
        "voice_threshold": 500,
        "max_conversation_exchanges": 3,
        "listen_duration": 3,
        "question_duration": 5,
        "greeting": "Assalomu alaykum! Sizga qanday yordam bera olaman?",
        "work_hours": "9:00 - 18:00",
        "address": "",
    },
    "updater": {
        "pip_path": "/opt/alisa/venv/bin/pip",
        "git_branch": None,  # Auto-detect current branch
    },
    "openai": {
        "api_key": None,
        "base_url": None,
    },
}

_config: dict | None = None


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base recursively."""
    result = base.copy()
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def get_config(config_path: str | None = None) -> dict:
    """Load config from YAML file, falling back to defaults."""
    global _config
    if _config is not None and config_path is None:
        return _config

    path = Path(config_path) if config_path else Path(
        os.environ.get("ALISA_CONFIG", "config.yaml")
    )

    config = _DEFAULTS.copy()
    if path.exists():
        try:
            with open(path) as f:
                loaded = yaml.safe_load(f) or {}
            config = _deep_merge(_DEFAULTS, loaded)
            logger.info("config_loaded", path=str(path))
        except Exception as e:
            logger.warning("config_load_failed", error=str(e), path=str(path))
    else:
        logger.info("config_using_defaults", path=str(path))

    # Override with environment variables
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        config["telegram"]["bot_token"] = os.environ["TELEGRAM_BOT_TOKEN"]
    if os.environ.get("TELEGRAM_CHAT_ID"):
        config["telegram"]["chat_id"] = os.environ["TELEGRAM_CHAT_ID"]
    if os.environ.get("OPENAI_API_KEY"):
        config["openai"]["api_key"] = os.environ["OPENAI_API_KEY"]
        # Also update in providers list
        for provider in config.get("llm", {}).get("providers", []):
            if provider.get("name") == "openai":
                provider["api_key"] = os.environ["OPENAI_API_KEY"]
    
    # Set API keys for all LLM providers from environment
    env_key_mapping = {
        "openai": "OPENAI_API_KEY",
        "gemini": "GEMINI_API_KEY", 
        "deepseek": "DEEPSEEK_API_KEY",
        "grok": "GROK_API_KEY",
        "claude": "CLAUDE_API_KEY"
    }
    
    for provider in config.get("llm", {}).get("providers", []):
        provider_name = provider.get("name")
        if provider_name in env_key_mapping:
            env_key = env_key_mapping[provider_name]
            if os.environ.get(env_key):
                provider["api_key"] = os.environ[env_key]
    
    # Backward compatibility warnings
    if "wake_word" in config and isinstance(config["wake_word"], dict):
        if "keyword" in config["wake_word"] and "wake_word" not in config:
            logger.warning("config_deprecated_wake_word_structure", 
                         message="Use top-level 'wake_word' string instead of wake_word.keyword")
    
    if "llm" not in config or "providers" not in config["llm"]:
        logger.warning("config_missing_llm_providers",
                      message="Missing llm.providers block - only Ollama will be available")

    _config = config
    return config


def reset_config():
    """Reset cached config (for testing)."""
    global _config
    _config = None
