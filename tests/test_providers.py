"""Tests for LLM providers."""

import pytest
import httpx
from unittest.mock import Mock, AsyncMock, patch

from alisa.brain.providers.base import LLMProvider
from alisa.brain.providers.openai import OpenAIProvider
from alisa.brain.providers.gemini import GeminiProvider
from alisa.brain.providers.deepseek import DeepSeekProvider
from alisa.brain.providers.grok import GrokProvider
from alisa.brain.providers.claude import ClaudeProvider
from alisa.brain.providers.ollama import OllamaProvider


class TestBaseLLMProvider:
    """Test base LLM provider."""
    
    def test_provider_initialization(self):
        """Test provider initialization."""
        config = {
            "name": "test_provider",
            "model": "test_model",
            "api_key": "test_key",
            "base_url": "https://api.test.com"
        }
        
        # Use concrete implementation for testing
        provider = OpenAIProvider(config)
        
        assert provider.name == "test_provider"
        assert provider.model == "test_model"
        assert provider.api_key == "test_key"
        assert provider.base_url == "https://api.test.com"
    
    def test_is_available_with_api_key(self):
        """Test availability check with API key."""
        config = {"name": "test", "api_key": "key"}
        provider = OpenAIProvider(config)
        assert provider.is_available() is True
    
    def test_is_available_without_api_key(self):
        """Test availability check without API key."""
        config = {"name": "test", "api_key": ""}
        provider = OpenAIProvider(config)
        assert provider.is_available() is False
    
    def test_is_available_ollama_exception(self):
        """Test that Ollama is available without API key."""
        config = {"name": "ollama", "api_key": ""}
        provider = OllamaProvider(config)
        assert provider.is_available() is True


class TestOpenAIProvider:
    """Test OpenAI provider."""
    
    def test_initialization(self):
        """Test OpenAI provider initialization."""
        config = {"name": "openai", "model": "gpt-4o-mini", "api_key": "test_key"}
        provider = OpenAIProvider(config)
        
        assert provider.name == "openai"
        assert provider.model == "gpt-4o-mini"
        assert provider.base_url == "https://api.openai.com/v1"
    
    def test_env_var_override(self):
        """Test environment variable override for API key."""
        config = {"name": "openai", "api_key": "config_key"}
        
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'env_key'}):
            provider = OpenAIProvider(config)
            assert provider.api_key == "env_key"
    
    @pytest.mark.asyncio
    async def test_generate_success(self):
        """Test successful generation."""
        config = {"name": "openai", "model": "gpt-4o-mini", "api_key": "test_key"}
        provider = OpenAIProvider(config)
        
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Test response"}}]
        }
        mock_response.raise_for_status.return_value = None
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            response = await provider.generate("Test prompt", "System prompt")
            
            assert response == "Test response"
    
    @pytest.mark.asyncio
    async def test_generate_no_api_key(self):
        """Test generation without API key."""
        config = {"name": "openai", "model": "gpt-4o-mini", "api_key": ""}
        provider = OpenAIProvider(config)
        
        with pytest.raises(ValueError, match="OpenAI API key not configured"):
            await provider.generate("Test prompt")


class TestGeminiProvider:
    """Test Gemini provider."""
    
    def test_initialization(self):
        """Test Gemini provider initialization."""
        config = {"name": "gemini", "model": "gemini-2.0-flash", "api_key": "test_key"}
        provider = GeminiProvider(config)
        
        assert provider.name == "gemini"
        assert provider.model == "gemini-2.0-flash"
        assert provider.base_url == "https://generativelanguage.googleapis.com/v1beta"
    
    @pytest.mark.asyncio
    async def test_generate_success(self):
        """Test successful generation."""
        config = {"name": "gemini", "model": "gemini-2.0-flash", "api_key": "test_key"}
        provider = GeminiProvider(config)
        
        mock_response = Mock()
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Test response"}]}}]
        }
        mock_response.raise_for_status.return_value = None
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            response = await provider.generate("Test prompt", "System prompt")
            
            assert response == "Test response"


class TestDeepSeekProvider:
    """Test DeepSeek provider."""
    
    def test_initialization(self):
        """Test DeepSeek provider initialization."""
        config = {"name": "deepseek", "model": "deepseek-chat", "api_key": "test_key"}
        provider = DeepSeekProvider(config)
        
        assert provider.name == "deepseek"
        assert provider.model == "deepseek-chat"
        assert provider.base_url == "https://api.deepseek.com/v1"
    
    @pytest.mark.asyncio
    async def test_generate_success(self):
        """Test successful generation."""
        config = {"name": "deepseek", "model": "deepseek-chat", "api_key": "test_key"}
        provider = DeepSeekProvider(config)
        
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Test response"}}]
        }
        mock_response.raise_for_status.return_value = None
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            response = await provider.generate("Test prompt")
            
            assert response == "Test response"


class TestGrokProvider:
    """Test Grok provider."""
    
    def test_initialization(self):
        """Test Grok provider initialization."""
        config = {"name": "grok", "model": "grok-2", "api_key": "test_key"}
        provider = GrokProvider(config)
        
        assert provider.name == "grok"
        assert provider.model == "grok-2"
        assert provider.base_url == "https://api.x.ai/v1"
    
    @pytest.mark.asyncio
    async def test_generate_success(self):
        """Test successful generation."""
        config = {"name": "grok", "model": "grok-2", "api_key": "test_key"}
        provider = GrokProvider(config)
        
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Test response"}}]
        }
        mock_response.raise_for_status.return_value = None
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            response = await provider.generate("Test prompt")
            
            assert response == "Test response"


class TestClaudeProvider:
    """Test Claude provider."""
    
    def test_initialization(self):
        """Test Claude provider initialization."""
        config = {"name": "claude", "model": "claude-sonnet-4-20250514", "api_key": "test_key"}
        provider = ClaudeProvider(config)
        
        assert provider.name == "claude"
        assert provider.model == "claude-sonnet-4-20250514"
        assert provider.base_url == "https://api.anthropic.com/v1"
    
    @pytest.mark.asyncio
    async def test_generate_success(self):
        """Test successful generation."""
        config = {"name": "claude", "model": "claude-sonnet-4-20250514", "api_key": "test_key"}
        provider = ClaudeProvider(config)
        
        mock_response = Mock()
        mock_response.json.return_value = {
            "content": [{"text": "Test response"}]
        }
        mock_response.raise_for_status.return_value = None
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            response = await provider.generate("Test prompt", "System prompt")
            
            assert response == "Test response"


class TestOllamaProvider:
    """Test Ollama provider."""
    
    def test_initialization(self):
        """Test Ollama provider initialization."""
        config = {"name": "ollama", "model": "qwen2.5:3b"}
        provider = OllamaProvider(config)
        
        assert provider.name == "ollama"
        assert provider.model == "qwen2.5:3b"
        assert provider.base_url == "http://localhost:11434"
    
    def test_is_available(self):
        """Test that Ollama is always available."""
        config = {"name": "ollama", "model": "qwen2.5:3b", "api_key": ""}
        provider = OllamaProvider(config)
        assert provider.is_available() is True
    
    @pytest.mark.asyncio
    async def test_generate_success(self):
        """Test successful generation."""
        config = {"name": "ollama", "model": "qwen2.5:3b"}
        provider = OllamaProvider(config)
        
        mock_response = Mock()
        mock_response.json.return_value = {"response": "Test response"}
        mock_response.raise_for_status.return_value = None
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            response = await provider.generate("Test prompt", "System prompt")
            
            assert response == "Test response"
