"""Tests for quick_test.py functionality."""

import pytest
import asyncio
from unittest.mock import patch, MagicMock

from alisa.brain.llm_manager import LLMManager


class TestQuickTest:
    """Test quick_test.py functionality."""
    
    def test_llm_manager_status_format(self):
        """Test that LLM manager status is properly formatted."""
        # Create a mock LLM manager
        manager = LLMManager()
        
        # Get status
        status = manager.get_provider_status()
        
        # Verify structure
        assert isinstance(status, dict)
        assert "active_providers" in status
        assert "last_successful" in status
        assert "providers" in status
        assert isinstance(status["providers"], dict)
        
        # Verify each provider has required fields
        for provider_name, provider_status in status["providers"].items():
            assert "available" in provider_status
            assert "requests" in provider_status
            assert "success_rate" in provider_status
            assert "avg_response_time" in provider_status
            assert "last_used" in provider_status
            assert "last_error" in provider_status
    
    @pytest.mark.asyncio
    async def test_llm_manager_generate_no_providers(self):
        """Test LLM manager behavior with no providers."""
        # Mock config with no providers
        mock_config = {
            "llm": {
                "timeout_sec": 5,
                "local_timeout_sec": 10,
                "providers": []  # No providers
            }
        }
        
        with patch('alisa.brain.llm_manager.get_config', return_value=mock_config):
            manager = LLMManager()
            
            # Should return Uzbek error message for no providers
            response = await manager.generate("Test prompt")
            assert "Kechirasiz" in response
            assert "LLM mavjud emas" in response
    
    def test_provider_status_structure(self):
        """Test that provider status has correct structure for quick_test."""
        manager = LLMManager()
        status = manager.get_provider_status()
        
        # Test the structure that quick_test.py expects
        providers = status.get("providers", {})
        active_count = status.get("active_providers", 0)
        
        assert isinstance(providers, dict)
        assert isinstance(active_count, int)
        
        # Each provider should have the fields quick_test expects
        for name, provider_info in providers.items():
            assert isinstance(provider_info["available"], bool)
            assert isinstance(provider_info["success_rate"], str)
            assert "%" in provider_info["success_rate"]
