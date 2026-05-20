"""Tests for LLM Manager and multi-provider fallback chain."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

from alisa.brain.llm_manager import LLMManager, get_llm_manager
from alisa.brain.providers.base import LLMProvider


class MockProvider(LLMProvider):
    """Mock provider for testing."""
    
    def __init__(self, config, should_fail=False, response="Test response"):
        super().__init__(config)
        self.should_fail = should_fail
        self.response = response
        self.call_count = 0
    
    async def generate(self, prompt, system_prompt=None):
        self.call_count += 1
        if self.should_fail:
            raise Exception("Mock provider error")
        return self.response


@pytest.fixture
def mock_config():
    """Mock config for testing."""
    return {
        "llm": {
            "timeout_sec": 2,
            "local_timeout_sec": 5,
            "providers": [
                {"name": "provider1", "api_key": "key1", "model": "model1"},
                {"name": "provider2", "api_key": "key2", "model": "model2"},
                {"name": "ollama", "model": "qwen2.5:3b", "base_url": "http://localhost:11434"},
            ]
        }
    }


@pytest.fixture
def llm_manager(mock_config):
    """Create LLM manager with mock providers."""
    with patch('alisa.brain.llm_manager.get_config', return_value=mock_config):
        manager = LLMManager()
        # Replace with mock providers
        manager.providers = [
            MockProvider({"name": "provider1"}, should_fail=False, response="Response from provider1"),
            MockProvider({"name": "provider2"}, should_fail=True),
            MockProvider({"name": "ollama"}, should_fail=False, response="Response from ollama"),
        ]
        # Initialize stats
        for provider in manager.providers:
            manager.provider_stats[provider.name] = {
                "requests": 0,
                "successes": 0,
                "failures": 0,
                "avg_response_time": 0.0,
                "last_used": None,
                "last_error": None,
            }
        return manager


class TestLLMManager:
    """Test LLM Manager functionality."""
    
    @pytest.mark.asyncio
    async def test_generate_success_first_provider(self, llm_manager):
        """Test successful generation with first provider."""
        response = await llm_manager.generate("Test prompt")
        
        assert response == "Response from provider1"
        assert llm_manager.last_successful_provider == "provider1"
        assert llm_manager.providers[0].call_count == 1
        assert llm_manager.providers[1].call_count == 0  # Should not be called
    
    @pytest.mark.asyncio
    async def test_fallback_to_second_provider(self, llm_manager):
        """Test fallback when first provider fails."""
        # Make first provider fail
        llm_manager.providers[0].should_fail = True
        
        response = await llm_manager.generate("Test prompt")
        
        assert response == "Response from ollama"  # Should fallback to ollama (3rd provider)
        assert llm_manager.last_successful_provider == "ollama"
        assert llm_manager.providers[0].call_count == 1  # First tried
        assert llm_manager.providers[1].call_count == 1  # Second tried (failed)
        assert llm_manager.providers[2].call_count == 1  # Third succeeded
    
    @pytest.mark.asyncio
    async def test_all_providers_fail(self, llm_manager):
        """Test when all providers fail."""
        # Make all providers fail
        for provider in llm_manager.providers:
            provider.should_fail = True
        
        response = await llm_manager.generate("Test prompt")
        
        assert response == "Kechirasiz, javob bera olmadim."
        assert all(p.call_count == 1 for p in llm_manager.providers)
    
    @pytest.mark.asyncio
    async def test_provider_reordering(self, llm_manager):
        """Test that last successful provider is tried first."""
        # First call - provider1 succeeds
        await llm_manager.generate("Test prompt 1")
        assert llm_manager.last_successful_provider == "provider1"
        
        # Make provider1 fail, provider2 succeed
        llm_manager.providers[0].should_fail = True
        llm_manager.providers[1].should_fail = False
        llm_manager.providers[1].response = "Response from provider2"
        
        # Second call - should try provider1 first (last successful), then fallback
        response = await llm_manager.generate("Test prompt 2")
        assert response == "Response from provider2"
        assert llm_manager.last_successful_provider == "provider2"
    
    @pytest.mark.asyncio
    async def test_timeout_handling(self, llm_manager):
        """Test timeout handling."""
        async def slow_generate(prompt, system_prompt=None):
            await asyncio.sleep(3)  # Longer than timeout
            return "Slow response"
        
        llm_manager.providers[0].generate = slow_generate
        
        response = await llm_manager.generate("Test prompt")
        
        # Should fallback to ollama after timeout
        assert response == "Response from ollama"
        assert llm_manager.provider_stats["provider1"]["failures"] == 1
        assert "Timeout" in llm_manager.provider_stats["provider1"]["last_error"]
    
    def test_get_provider_status(self, llm_manager):
        """Test provider status reporting."""
        # Simulate some usage
        llm_manager.provider_stats["provider1"]["requests"] = 10
        llm_manager.provider_stats["provider1"]["successes"] = 8
        llm_manager.provider_stats["provider1"]["failures"] = 2
        llm_manager.provider_stats["provider1"]["avg_response_time"] = 1.5
        llm_manager.last_successful_provider = "provider1"
        
        status = llm_manager.get_provider_status()
        
        assert status["active_providers"] == 3
        assert status["last_successful"] == "provider1"
        assert "provider1" in status["providers"]
        assert status["providers"]["provider1"]["success_rate"] == "80.0%"
        assert status["providers"]["provider1"]["avg_response_time"] == "1.50s"
    
    @pytest.mark.asyncio
    async def test_empty_response_handling(self, llm_manager):
        """Test handling of empty responses."""
        llm_manager.providers[0].response = ""  # Empty response
        
        response = await llm_manager.generate("Test prompt")
        
        # Should fallback to next provider
        assert response == "Response from ollama"
        assert llm_manager.provider_stats["provider1"]["failures"] == 1
        assert "Empty response" in llm_manager.provider_stats["provider1"]["last_error"]


class TestGlobalLLMManager:
    """Test global LLM manager instance."""
    
    def test_get_llm_manager_singleton(self):
        """Test that get_llm_manager returns singleton."""
        with patch('alisa.brain.llm_manager.get_config', return_value={"llm": {"providers": []}}):
            manager1 = get_llm_manager()
            manager2 = get_llm_manager()
            assert manager1 is manager2
    
    @pytest.mark.asyncio
    async def test_generate_with_fallback(self):
        """Test generate_with_fallback function."""
        from alisa.brain.llm_manager import generate_with_fallback
        
        with patch('alisa.brain.llm_manager.get_llm_manager') as mock_get_manager:
            mock_manager = Mock()
            mock_manager.generate = AsyncMock(return_value="Test response")
            mock_get_manager.return_value = mock_manager
            
            response = await generate_with_fallback("Test prompt", "System prompt")
            
            assert response == "Test response"
            mock_manager.generate.assert_called_once_with("Test prompt", "System prompt")
