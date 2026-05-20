"""Tests for setup/verify_deployment.py"""

import pytest
from unittest.mock import Mock, patch
from pathlib import Path
import sys
import subprocess

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from setup.verify_deployment import (
    run_brief_acceptance_tests,
    check_config_completeness,
    check_llm_manager,
    check_system_prompt,
    check_telegram_handlers
)


class TestDeploymentVerification:
    """Test deployment verification functionality."""
    
    def test_brief_acceptance_tests_success(self):
        """Test brief acceptance tests when they pass."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="===== 16 passed in 2.40s =====",
                stderr=""
            )
            
            checks = run_brief_acceptance_tests()
            
            assert len(checks) == 1
            assert checks[0][0] == "✅"
            assert "Brief acceptance tests" in checks[0][1]
    
    def test_brief_acceptance_tests_failure(self):
        """Test brief acceptance tests when they fail."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=1,
                stdout="FAILED tests/test_brief_acceptance.py::test_something",
                stderr=""
            )
            
            checks = run_brief_acceptance_tests()
            
            assert len(checks) >= 1
            assert checks[0][0] == "❌"
            assert "FAILED" in checks[0][1]
    
    def test_brief_acceptance_tests_timeout(self):
        """Test brief acceptance tests timeout handling."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("pytest", 60)
            
            checks = run_brief_acceptance_tests()
            
            assert len(checks) == 1
            assert checks[0][0] == "❌"
            assert "Timeout" in checks[0][1]
    
    @patch('setup.verify_deployment.get_config')
    @patch('setup.verify_deployment.reset_config')
    def test_config_completeness_success(self, mock_reset, mock_get_config):
        """Test config completeness check with valid config."""
        mock_get_config.return_value = {
            'language': 'uz',
            'wake_word': {'keyword': 'alisa'},
            'llm': {
                'providers': [
                    {'name': 'openai'},
                    {'name': 'gemini'},
                    {'name': 'deepseek'},
                    {'name': 'grok'},
                    {'name': 'claude'},
                    {'name': 'ollama'}
                ]
            },
            'whisper': {'model': 'base.bin'},
            'piper': {'model': 'uz_UZ-doniyorbek-medium'}
        }
        
        checks = check_config_completeness()
        
        # Should have multiple successful checks
        success_checks = [c for c in checks if c[0] == "✅"]
        assert len(success_checks) >= 4  # Language, wake word, providers, ollama last
    
    @patch('setup.verify_deployment.get_config')
    @patch('setup.verify_deployment.reset_config')
    def test_config_completeness_missing_language(self, mock_reset, mock_get_config):
        """Test config completeness check with missing language."""
        mock_get_config.return_value = {
            'language': 'en',  # Wrong language
            'wake_word': {'keyword': 'alisa'},
            'llm': {'providers': []}
        }
        
        checks = check_config_completeness()
        
        # Should have failed language check
        failed_checks = [c for c in checks if c[0] == "❌" and "Language" in c[1]]
        assert len(failed_checks) == 1
    
    @patch('setup.verify_deployment.LLMManager')
    @patch('setup.verify_deployment.reset_config')
    def test_llm_manager_check_success(self, mock_reset, mock_llm_manager):
        """Test LLM manager check with providers loaded."""
        mock_manager = Mock()
        mock_manager.providers = [
            Mock(name='openai'),
            Mock(name='ollama')
        ]
        mock_llm_manager.return_value = mock_manager
        
        checks = check_llm_manager()
        
        # Should have successful checks
        success_checks = [c for c in checks if c[0] == "✅"]
        assert len(success_checks) >= 2  # Providers loaded, ollama available
    
    @patch('alisa.core.assistant.ALISA_SYSTEM_PROMPT_UZ', 
           "Sen Alisa - aqlli yordamchi. Sen faqat o'zbek tilida gaplashasan.")
    def test_system_prompt_check_success(self):
        """Test system prompt check with valid Uzbek prompt."""
        checks = check_system_prompt()
        
        assert len(checks) == 1
        assert checks[0][0] == "✅"
        assert "Uzbek system prompt" in checks[0][1]
    
    @patch('alisa.core.assistant.ALISA_SYSTEM_PROMPT_UZ', "")
    def test_system_prompt_check_missing(self):
        """Test system prompt check with missing prompt."""
        checks = check_system_prompt()
        
        assert len(checks) == 1
        assert checks[0][0] == "❌"
        assert "not found or empty" in checks[0][1]
    
    @patch('alisa.telegram.bot.AlisaBot')
    def test_telegram_handlers_check_success(self, mock_bot_class):
        """Test telegram handlers check with all handlers present."""
        mock_bot_class.status_command = Mock()
        mock_bot_class.providers_command = Mock()
        mock_bot_class.ask_command = Mock()
        
        checks = check_telegram_handlers()
        
        success_checks = [c for c in checks if c[0] == "✅"]
        assert len(success_checks) == 3  # All three handlers
    
    def test_telegram_handlers_check_import_error(self):
        """Test telegram handlers check with import error."""
        with patch('builtins.__import__', side_effect=ImportError("Module not found")):
            checks = check_telegram_handlers()
            
            assert len(checks) == 1
            assert checks[0][0] == "❌"
            assert "import failed" in checks[0][1]
