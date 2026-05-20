"""Tests for web dashboard service."""

import pytest
import asyncio
import warnings
from unittest.mock import Mock, patch, AsyncMock

# Suppress aiohttp deprecation warnings for cleaner test output
warnings.filterwarnings("ignore", category=DeprecationWarning, module="aiohttp.*")

from alisa.services.web_dashboard import AlisaWebDashboard, get_web_dashboard


class TestWebDashboardIntegration:
    """Test web dashboard integration."""
    
    @patch('alisa.services.web_dashboard.get_system_stats')
    @patch('alisa.services.web_dashboard.is_system_healthy')
    @patch('alisa.services.web_dashboard.get_cpu_temperature')
    @patch('alisa.services.web_dashboard.get_llm_manager')
    @patch('alisa.services.web_dashboard.get_config')
    def test_dashboard_initialization(self, mock_config, mock_llm, mock_temp, mock_healthy, mock_stats):
        """Test dashboard can be initialized."""
        mock_config.return_value = {}
        mock_stats.return_value = {}
        mock_healthy.return_value = True
        mock_temp.return_value = 42.0
        mock_llm.return_value = Mock()
        
        dashboard = AlisaWebDashboard(port=8080)
        
        assert dashboard.port == 8080
        assert dashboard.app is not None
        assert dashboard.llm_manager is not None
        assert dashboard.config is not None
    
    @patch('alisa.services.web_dashboard.get_system_stats')
    @patch('alisa.services.web_dashboard.is_system_healthy')
    @patch('alisa.services.web_dashboard.get_cpu_temperature')
    @patch('alisa.services.web_dashboard.get_llm_manager')
    @patch('alisa.services.web_dashboard.get_config')
    def test_get_web_dashboard_singleton(self, mock_config, mock_llm, mock_temp, mock_healthy, mock_stats):
        """Test get_web_dashboard returns singleton."""
        mock_config.return_value = {}
        mock_stats.return_value = {}
        mock_healthy.return_value = True
        mock_temp.return_value = 42.0
        mock_llm.return_value = Mock()
        
        # Clear global instance
        import alisa.services.web_dashboard
        alisa.services.web_dashboard._dashboard = None
        
        dashboard1 = get_web_dashboard(port=8080)
        dashboard2 = get_web_dashboard(port=8081)  # Port ignored for singleton
        
        assert dashboard1 is dashboard2
        assert dashboard1.port == 8080
    
    @patch('alisa.services.web_dashboard.get_system_stats')
    @patch('alisa.services.web_dashboard.is_system_healthy')
    @patch('alisa.services.web_dashboard.get_cpu_temperature')
    @patch('alisa.services.web_dashboard.get_llm_manager')
    @patch('alisa.services.web_dashboard.get_config')
    def test_health_api_success(self, mock_config, mock_llm, mock_temp, mock_healthy, mock_stats):
        """Test health API success response."""
        mock_config.return_value = {}
        mock_stats.return_value = {
            "cpu_percent": 25.5,
            "memory_percent": 45.2,
            "disk_percent": 60.1,
            "uptime_hours": 48.5
        }
        mock_healthy.return_value = True
        mock_temp.return_value = 42.5
        mock_llm.return_value = Mock()
        
        dashboard = AlisaWebDashboard()
        
        # Create mock request
        request = Mock()
        
        # Test success response
        async def test_success():
            response = await dashboard._health_api(request)
            assert response.status == 200
            # Check that response contains expected data
            assert hasattr(response, '_body')
        
        asyncio.run(test_success())
    
    @patch('alisa.services.web_dashboard.get_system_stats')
    @patch('alisa.services.web_dashboard.is_system_healthy')
    @patch('alisa.services.web_dashboard.get_cpu_temperature')
    @patch('alisa.services.web_dashboard.get_llm_manager')
    @patch('alisa.services.web_dashboard.get_config')
    def test_health_api_error_handling(self, mock_config, mock_llm, mock_temp, mock_healthy, mock_stats):
        """Test health API error handling."""
        mock_config.return_value = {}
        mock_llm.return_value = Mock()
        mock_stats.side_effect = Exception("Health error")
        
        dashboard = AlisaWebDashboard()
        
        # Create mock request
        request = Mock()
        
        # Test error handling
        async def test_error():
            response = await dashboard._health_api(request)
            assert response.status == 500
            # Check that response contains error
            assert hasattr(response, '_body')
        
        asyncio.run(test_error())
    
    @patch('alisa.services.web_dashboard.get_system_stats')
    @patch('alisa.services.web_dashboard.is_system_healthy')
    @patch('alisa.services.web_dashboard.get_cpu_temperature')
    @patch('alisa.services.web_dashboard.get_llm_manager')
    @patch('alisa.services.web_dashboard.get_config')
    def test_providers_api_success(self, mock_config, mock_llm, mock_temp, mock_healthy, mock_stats):
        """Test providers API success response."""
        mock_config.return_value = {}
        mock_stats.return_value = {}
        mock_healthy.return_value = True
        mock_temp.return_value = 42.0
        
        # Mock provider
        mock_provider = Mock()
        mock_provider.name = "openai"
        mock_provider.is_available.return_value = True
        mock_provider.model = "gpt-4o-mini"
        
        mock_llm.return_value.providers = [mock_provider]
        mock_llm.return_value.last_successful_provider = "openai"
        
        dashboard = AlisaWebDashboard()
        
        # Create mock request
        request = Mock()
        
        # Test success response
        async def test_success():
            response = await dashboard._providers_api(request)
            assert response.status == 200
            assert hasattr(response, '_body')
        
        asyncio.run(test_success())
    
    @patch('alisa.services.web_dashboard.get_system_stats')
    @patch('alisa.services.web_dashboard.is_system_healthy')
    @patch('alisa.services.web_dashboard.get_cpu_temperature')
    @patch('alisa.services.web_dashboard.get_llm_manager')
    @patch('alisa.services.web_dashboard.get_config')
    def test_providers_api_error_handling(self, mock_config, mock_llm, mock_temp, mock_healthy, mock_stats):
        """Test providers API error handling."""
        mock_config.return_value = {}
        mock_stats.return_value = {}
        mock_healthy.return_value = True
        mock_temp.return_value = 42.0
        mock_llm.return_value.providers = []
        mock_llm.return_value.last_successful_provider = None
        
        # Make providers access fail
        mock_llm.return_value.providers = Mock()
        mock_llm.return_value.providers.__iter__ = Mock(side_effect=Exception("Provider error"))
        
        dashboard = AlisaWebDashboard()
        
        # Create mock request
        request = Mock()
        
        # Test error handling
        async def test_error():
            response = await dashboard._providers_api(request)
            assert response.status == 500
            assert hasattr(response, '_body')
        
        asyncio.run(test_error())
    
    @patch('alisa.services.web_dashboard.get_system_stats')
    @patch('alisa.services.web_dashboard.is_system_healthy')
    @patch('alisa.services.web_dashboard.get_cpu_temperature')
    @patch('alisa.services.web_dashboard.get_llm_manager')
    @patch('alisa.services.web_dashboard.get_config')
    def test_config_api_success(self, mock_config, mock_llm, mock_temp, mock_healthy, mock_stats):
        """Test config API success response."""
        mock_stats.return_value = {}
        mock_healthy.return_value = True
        mock_temp.return_value = 42.0
        mock_llm.return_value = Mock()
        mock_config.return_value = {
            "language": "uz",
            "wake_word": "alisa",
            "stt": {"model": "tiny"},
            "tts": {"model": "uz_UZ-doniyorbek-medium"},
            "llm": {"providers": [{"name": "openai"}, {"name": "gemini"}]}
        }
        
        dashboard = AlisaWebDashboard()
        
        # Create mock request
        request = Mock()
        
        # Test success response
        async def test_success():
            response = await dashboard._config_api(request)
            assert response.status == 200
            assert hasattr(response, '_body')
        
        asyncio.run(test_success())
    
    @patch('alisa.services.web_dashboard.get_system_stats')
    @patch('alisa.services.web_dashboard.is_system_healthy')
    @patch('alisa.services.web_dashboard.get_cpu_temperature')
    @patch('alisa.services.web_dashboard.get_llm_manager')
    @patch('alisa.services.web_dashboard.get_config')
    def test_config_api_error_handling(self, mock_config, mock_llm, mock_temp, mock_healthy, mock_stats):
        """Test config API error handling."""
        mock_stats.return_value = {}
        mock_healthy.return_value = True
        mock_temp.return_value = 42.0
        mock_llm.return_value = Mock()
        mock_config.return_value.get = Mock(side_effect=Exception("Config error"))
        
        dashboard = AlisaWebDashboard()
        
        # Create mock request
        request = Mock()
        
        # Test error handling
        async def test_error():
            response = await dashboard._config_api(request)
            assert response.status == 500
            assert hasattr(response, '_body')
        
        asyncio.run(test_error())


class TestWebDashboardLifecycle:
    """Test web dashboard lifecycle management."""
    
    @pytest.mark.asyncio
    @patch('alisa.services.web_dashboard.get_system_stats')
    @patch('alisa.services.web_dashboard.is_system_healthy')
    @patch('alisa.services.web_dashboard.get_cpu_temperature')
    @patch('alisa.services.web_dashboard.get_llm_manager')
    @patch('alisa.services.web_dashboard.get_config')
    async def test_start_stop_dashboard(self, mock_config, mock_llm, mock_temp, mock_healthy, mock_stats):
        """Test dashboard start and stop."""
        mock_config.return_value = {}
        mock_stats.return_value = {}
        mock_healthy.return_value = True
        mock_temp.return_value = 42.0
        mock_llm.return_value = Mock()
        
        dashboard = AlisaWebDashboard(port=0)  # Use port 0 for testing
        
        # Start dashboard
        runner = await dashboard.start()
        assert runner is not None
        
        # Stop dashboard
        await dashboard.stop(runner)
        
        # Should complete without errors
    
    @pytest.mark.asyncio
    @patch('alisa.services.web_dashboard.get_system_stats')
    @patch('alisa.services.web_dashboard.is_system_healthy')
    @patch('alisa.services.web_dashboard.get_cpu_temperature')
    @patch('alisa.services.web_dashboard.get_llm_manager')
    @patch('alisa.services.web_dashboard.get_config')
    async def test_start_dashboard_error(self, mock_config, mock_llm, mock_temp, mock_healthy, mock_stats):
        """Test dashboard start error handling."""
        mock_config.return_value = {}
        mock_stats.return_value = {}
        mock_healthy.return_value = True
        mock_temp.return_value = 42.0
        mock_llm.return_value = Mock()
        
        dashboard = AlisaWebDashboard(port=-1)  # Invalid port
        
        # Should raise exception for invalid port
        with pytest.raises(Exception):
            await dashboard.start()
