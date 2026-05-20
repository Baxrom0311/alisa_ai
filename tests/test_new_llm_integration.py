"""Test for new LLM integration with multi-provider manager."""

import pytest
from unittest.mock import patch, AsyncMock

from alisa.brain.llm_manager import LLMManager, generate_with_fallback


class TestNewLLMIntegration:
    """Test new LLM integration with multi-provider manager."""
    
    @pytest.mark.asyncio
    async def test_generate_with_fallback_uses_manager(self):
        """Test that generate_with_fallback uses the LLM manager."""
        with patch('alisa.brain.llm_manager.get_llm_manager') as mock_get_manager:
            mock_manager = AsyncMock()
            mock_manager.generate = AsyncMock(return_value="Manager response")
            mock_get_manager.return_value = mock_manager
            
            result = await generate_with_fallback("Test prompt", "System prompt")
            
            assert result == "Manager response"
            mock_manager.generate.assert_called_once_with("Test prompt", "System prompt")
    
    @pytest.mark.asyncio
    async def test_llm_manager_direct_usage(self):
        """Test using LLMManager directly."""
        # Mock config with no providers to test fallback message
        mock_config = {
            "llm": {
                "timeout_sec": 5,
                "local_timeout_sec": 10,
                "providers": []  # No providers
            }
        }
        
        with patch('alisa.brain.llm_manager.get_config', return_value=mock_config):
            manager = LLMManager()
            
            result = await manager.generate("Test prompt")
            assert "LLM mavjud emas" in result
    
    @pytest.mark.asyncio
    async def test_llm_manager_provider_fallback(self):
        """Test LLM manager provider fallback logic."""
        # Mock config with multiple providers
        mock_config = {
            "llm": {
                "timeout_sec": 1,  # Short timeout for testing
                "local_timeout_sec": 1,
                "providers": [
                    {"name": "openai", "api_key": "test", "model": "gpt-4o-mini"},
                    {"name": "ollama", "model": "qwen2.5:3b"}
                ]
            }
        }
        
        with patch('alisa.brain.llm_manager.get_config', return_value=mock_config):
            manager = LLMManager()
            
            # Mock providers to simulate failure then success
            mock_provider1 = AsyncMock()
            mock_provider1.name = "openai"
            mock_provider1.generate = AsyncMock(side_effect=Exception("API error"))
            
            mock_provider2 = AsyncMock()
            mock_provider2.name = "ollama"
            mock_provider2.generate = AsyncMock(return_value="Ollama response")
            
            manager.providers = [mock_provider1, mock_provider2]
            
            # Initialize stats for mock providers
            for provider in manager.providers:
                manager.provider_stats[provider.name] = {
                    "requests": 0,
                    "successes": 0,
                    "failures": 0,
                    "avg_response_time": 0.0,
                    "last_used": 0,
                    "last_error": None,
                }
            
            result = await manager.generate("Test prompt")
            
            assert result == "Ollama response"
            assert manager.last_successful_provider == "ollama"
