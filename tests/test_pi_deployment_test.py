"""Tests for Pi deployment test script."""

import asyncio
import pytest
from unittest.mock import Mock, patch, AsyncMock
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from setup.pi_deployment_test import PiDeploymentTester


class TestPiDeploymentTester:
    """Test the Pi deployment tester."""
    
    @pytest.fixture
    def tester(self):
        """Create a deployment tester instance."""
        return PiDeploymentTester()
    
    @pytest.mark.asyncio
    async def test_system_validation(self, tester):
        """Test system validation test."""
        with patch('setup.pi_deployment_test.validate_system') as mock_validate, \
             patch('setup.pi_deployment_test.get_system_info') as mock_info:
            
            mock_validate.return_value = (True, [])
            mock_info.return_value = {
                "memory_gb": 4,
                "architecture": "aarch64"
            }
            
            result = await tester.test_system_validation()
            
            assert result["status"] == "passed"
            assert "system_info" in result
            mock_validate.assert_called_once()
            mock_info.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_system_validation_with_warnings(self, tester):
        """Test system validation with warnings."""
        with patch('setup.pi_deployment_test.validate_system') as mock_validate, \
             patch('setup.pi_deployment_test.get_system_info') as mock_info:
            
            mock_validate.return_value = (False, ["Missing dependency"])
            mock_info.return_value = {
                "memory_gb": 2,  # Low memory
                "architecture": "x86_64"  # Not ARM
            }
            
            result = await tester.test_system_validation()
            
            assert result["status"] == "warning"
            assert len(result["warnings"]) >= 3  # Original issue + low memory + not ARM
    
    @pytest.mark.asyncio
    async def test_config_validation(self, tester):
        """Test configuration validation."""
        with patch('setup.pi_deployment_test.get_config') as mock_config:
            mock_config.return_value = {
                "llm": {"providers": [{"api_key": "test"}, {"api_key": ""}]},
                "whisper": {},
                "piper": {},
                "telegram": {}
            }
            
            result = await tester.test_config_validation()
            
            assert result["status"] == "passed"
            assert result["api_keys_configured"] == 1
            assert result["total_providers"] == 2
    
    @pytest.mark.asyncio
    async def test_config_validation_missing_sections(self, tester):
        """Test config validation with missing sections."""
        with patch('setup.pi_deployment_test.get_config') as mock_config:
            mock_config.return_value = {
                "llm": {"providers": []},
                # Missing whisper, piper, telegram
            }
            
            result = await tester.test_config_validation()
            
            assert result["status"] == "failed"
            assert "Missing config sections" in result["error"]
    
    @pytest.mark.asyncio
    async def test_llm_providers(self, tester):
        """Test LLM provider testing."""
        mock_manager = AsyncMock()
        mock_manager.generate.return_value = "OK"
        
        with patch('setup.pi_deployment_test.get_llm_manager', return_value=mock_manager):
            result = await tester.test_llm_providers()
            
            assert result["status"] == "passed"
            assert result["working_providers"] > 0
            assert "provider_results" in result
            assert result["fallback_working"] is True
    
    @pytest.mark.asyncio
    async def test_audio_system(self, tester):
        """Test audio system testing."""
        with patch('setup.pi_deployment_test.test_audio_devices') as mock_audio:
            mock_audio.return_value = {
                "input_available": True,
                "output_available": True
            }
            
            result = await tester.test_audio_system()
            
            assert result["status"] == "passed"
            assert result["audio_devices"]["input_available"] is True
            assert result["audio_devices"]["output_available"] is True
    
    @pytest.mark.asyncio
    async def test_audio_system_warning(self, tester):
        """Test audio system with missing devices."""
        with patch('setup.pi_deployment_test.test_audio_devices') as mock_audio:
            mock_audio.return_value = {
                "input_available": False,
                "output_available": True
            }
            
            result = await tester.test_audio_system()
            
            assert result["status"] == "warning"
            assert len(result["warnings"]) > 0
    
    @pytest.mark.asyncio
    async def test_voice_pipeline(self, tester):
        """Test voice pipeline testing."""
        with patch('alisa.voice.stt.transcribe') as mock_stt, \
             patch('alisa.voice.tts.synthesize') as mock_tts, \
             patch('setup.pi_deployment_test.asyncio.to_thread') as mock_thread:
            
            mock_thread.side_effect = lambda func, *args: func(*args)
            mock_stt.return_value = ""  # Empty string for silence
            mock_tts.return_value = "/tmp/test.wav"
            
            with patch('setup.pi_deployment_test.Path') as mock_path:
                mock_path.return_value.exists.return_value = True
                mock_path.return_value.unlink = Mock()
                
                result = await tester.test_voice_pipeline()
                
                assert result["status"] == "passed"
                assert result["stt_working"] is True
                assert result["tts_working"] is True
    
    @pytest.mark.asyncio
    async def test_telegram_bot_no_token(self, tester):
        """Test Telegram bot test without token."""
        with patch.dict('os.environ', {}, clear=True):
            result = await tester.test_telegram_bot()
            
            assert result["status"] == "skipped"
            assert "TELEGRAM_BOT_TOKEN not configured" in result["reason"]
    
    @pytest.mark.asyncio
    async def test_telegram_bot_with_token(self, tester):
        """Test Telegram bot test with token."""
        with patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': 'test_token'}), \
             patch('setup.pi_deployment_test.AlisaAssistant') as mock_assistant, \
             patch('setup.pi_deployment_test.AlisaBot') as mock_bot:
            
            result = await tester.test_telegram_bot()
            
            assert result["status"] == "passed"
            assert result["bot_initialized"] is True
    
    @pytest.mark.asyncio
    async def test_memory_management(self, tester):
        """Test memory management testing."""
        with patch('setup.pi_deployment_test.get_system_stats') as mock_stats, \
             patch('setup.pi_deployment_test.check_memory_pressure') as mock_pressure:
            
            mock_stats.side_effect = [
                {"memory_used_mb": 100},
                {"memory_used_mb": 101}
            ]
            mock_pressure.return_value = {"pressure_level": "normal"}
            
            result = await tester.test_memory_management()
            
            assert result["status"] == "passed"
            assert result["monitoring_working"] is True
            assert result["initial_memory_mb"] == 100
    
    @pytest.mark.asyncio
    async def test_performance_benchmarks(self, tester):
        """Test performance benchmarking."""
        mock_manager = AsyncMock()
        mock_manager.generate.return_value = "Hi"
        
        with patch('setup.pi_deployment_test.get_llm_manager', return_value=mock_manager), \
             patch('setup.pi_deployment_test.tempfile.NamedTemporaryFile') as mock_temp:
            
            mock_temp.return_value.__enter__.return_value.write = Mock()
            mock_temp.return_value.__enter__.return_value.flush = Mock()
            
            result = await tester.test_performance_benchmarks()
            
            assert result["status"] in ["passed", "warning"]
            assert "benchmarks" in result
            assert "llm_response_time" in result["benchmarks"]
    
    @pytest.mark.asyncio
    async def test_integration(self, tester):
        """Test integration testing."""
        mock_assistant = AsyncMock()
        mock_assistant.process_text.return_value = "Salom!"
        mock_assistant.memory.get_recent_messages.return_value = [{"role": "user", "content": "test"}]
        
        with patch('alisa.core.assistant.AlisaAssistant', return_value=mock_assistant):
            result = await tester.test_integration()
            
            assert result["status"] == "passed"
            assert result["text_processing_working"] is True
            assert result["memory_working"] is True
            assert result["response_length"] > 0
    
    @pytest.mark.asyncio
    async def test_run_all_tests(self, tester):
        """Test running all tests."""
        # Mock all test methods to return success
        test_methods = [
            'test_system_validation',
            'test_config_validation', 
            'test_llm_providers',
            'test_audio_system',
            'test_voice_pipeline',
            'test_telegram_bot',
            'test_memory_management',
            'test_performance_benchmarks',
            'test_integration'
        ]
        
        for method in test_methods:
            setattr(tester, method, AsyncMock(return_value={"status": "passed"}))
        
        report = await tester.run_all_tests()
        
        assert report["overall_status"] == "passed"
        assert report["tests_passed"] == len(test_methods)
        assert report["total_tests"] == len(test_methods)
        assert report["success_rate"] == 100.0
        assert report["deployment_ready"] is True
    
    @pytest.mark.asyncio
    async def test_run_all_tests_with_failures(self, tester):
        """Test running all tests with some failures."""
        # Mock some tests to fail
        tester.test_system_validation = AsyncMock(return_value={"status": "passed"})
        tester.test_config_validation = AsyncMock(return_value={"status": "failed", "error": "Config error"})
        tester.test_llm_providers = AsyncMock(return_value={"status": "passed"})
        tester.test_audio_system = AsyncMock(return_value={"status": "warning", "warnings": ["Audio warning"]})
        tester.test_voice_pipeline = AsyncMock(return_value={"status": "passed"})
        tester.test_telegram_bot = AsyncMock(return_value={"status": "passed"})
        tester.test_memory_management = AsyncMock(return_value={"status": "passed"})
        tester.test_performance_benchmarks = AsyncMock(return_value={"status": "passed"})
        tester.test_integration = AsyncMock(return_value={"status": "passed"})
        
        report = await tester.run_all_tests()
        
        assert report["overall_status"] == "failed"  # Has errors
        assert len(report["errors"]) == 1
        assert len(report["warnings"]) == 1
        assert report["deployment_ready"] is False  # Has errors, so not ready
    
    def test_generate_report(self, tester):
        """Test report generation."""
        tester.results = {
            "test1": {"status": "passed"},
            "test2": {"status": "failed", "error": "Test error"},
            "test3": {"status": "warning", "warnings": ["Test warning"]}
        }
        tester.errors = ["test2: Test error"]
        tester.warnings = ["test3: Test warning"]
        
        report = tester.generate_report()
        
        assert report["overall_status"] == "failed"  # Has errors
        assert report["tests_passed"] == 1
        assert report["total_tests"] == 3
        assert report["success_rate"] == 33.3
        assert len(report["errors"]) == 1
        assert len(report["warnings"]) == 1
        assert report["deployment_ready"] is False  # <80% pass rate


@pytest.mark.asyncio
async def test_main_function():
    """Test the main function."""
    with patch('setup.pi_deployment_test.PiDeploymentTester') as mock_tester_class, \
         patch('setup.pi_deployment_test.sys.exit') as mock_exit, \
         patch('builtins.print'):
        
        mock_tester = AsyncMock()
        mock_tester.run_all_tests.return_value = {
            "overall_status": "passed",
            "tests_passed": 9,
            "total_tests": 9,
            "success_rate": 100.0,
            "deployment_ready": True,
            "errors": [],
            "warnings": []
        }
        mock_tester_class.return_value = mock_tester
        
        from setup.pi_deployment_test import main
        await main()
        
        mock_exit.assert_called_once_with(0)
