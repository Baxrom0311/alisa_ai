"""Tests for alisa.brain.online module."""

import os
import pytest
from unittest.mock import patch, Mock

from alisa.brain.online import online_llm_fallback


class TestOnlineLLMFallback:
    """Test online LLM fallback functionality."""

    @patch('alisa.brain.online.is_online')
    @patch('alisa.brain.online.get_config')
    @patch('httpx.post')
    def test_online_llm_uses_env_api_key(self, mock_post, mock_get_config, mock_is_online):
        """Test that online_llm_fallback uses API key from environment."""
        # Mock online status
        mock_is_online.return_value = True
        
        # Mock config with env var precedence
        mock_get_config.return_value = {
            "openai": {
                "api_key": "env_api_key_value"
            }
        }
        
        # Mock successful HTTP response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Test response"}}]
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        # Call the function
        result = online_llm_fallback("test prompt")
        
        # Verify it used the API key from config
        assert result == "Test response"
        mock_post.assert_called_once()
        
        # Check that the Authorization header contains the env API key
        call_args = mock_post.call_args
        headers = call_args[1]['headers']
        assert headers['Authorization'] == 'Bearer env_api_key_value'

    @patch('alisa.brain.online.is_online')
    @patch('alisa.brain.online.get_config')
    def test_online_llm_no_api_key(self, mock_get_config, mock_is_online):
        """Test that online_llm_fallback returns None when no API key."""
        # Mock online status
        mock_is_online.return_value = True
        
        # Mock config with no API key
        mock_get_config.return_value = {
            "openai": {
                "api_key": None
            }
        }
        
        # Call the function
        result = online_llm_fallback("test prompt")
        
        # Should return None when no API key
        assert result is None

    @patch('alisa.brain.online.is_online')
    def test_online_llm_offline(self, mock_is_online):
        """Test that online_llm_fallback returns None when offline."""
        # Mock offline status
        mock_is_online.return_value = False
        
        # Call the function
        result = online_llm_fallback("test prompt")
        
        # Should return None when offline
        assert result is None
