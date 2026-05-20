"""Tests for health monitoring service."""

import pytest
from unittest.mock import patch, Mock, mock_open

from alisa.services.health import (
    get_system_stats, get_cpu_temperature, 
    format_system_status, is_system_healthy
)


class TestHealthMonitoring:
    """Test health monitoring functionality."""
    
    @patch('alisa.services.health.psutil.cpu_percent')
    @patch('alisa.services.health.psutil.virtual_memory')
    @patch('alisa.services.health.psutil.disk_usage')
    @patch('alisa.services.health.psutil.getloadavg')
    @patch('alisa.services.health.get_cpu_temperature')
    def test_get_system_stats_success(self, mock_temp, mock_load, 
                                     mock_disk, mock_memory, mock_cpu):
        """Test successful system stats collection."""
        # Mock psutil responses
        mock_cpu.return_value = 25.5
        
        mock_mem = Mock()
        mock_mem.percent = 45.2
        mock_mem.used = 1024 * 1024 * 1024  # 1GB
        mock_mem.total = 4 * 1024 * 1024 * 1024  # 4GB
        mock_memory.return_value = mock_mem
        
        mock_disk_info = Mock()
        mock_disk_info.used = 10 * 1024 * 1024 * 1024  # 10GB
        mock_disk_info.total = 64 * 1024 * 1024 * 1024  # 64GB
        mock_disk_info.free = 54 * 1024 * 1024 * 1024  # 54GB
        mock_disk.return_value = mock_disk_info
        
        mock_load.return_value = (0.5, 0.7, 0.9)
        mock_temp.return_value = 42.5
        
        stats = get_system_stats()
        
        assert stats["cpu_percent"] == 25.5
        assert stats["memory_percent"] == 45.2
        assert stats["memory_used_mb"] == 1024
        assert stats["memory_total_mb"] == 4096
        assert stats["temperature_c"] == 42.5
        assert stats["load_avg_1m"] == 0.5
    
    @patch('alisa.services.health.psutil.cpu_percent')
    def test_get_system_stats_error(self, mock_cpu):
        """Test system stats collection with error."""
        mock_cpu.side_effect = Exception("psutil error")
        
        stats = get_system_stats()
        assert stats == {}
    
    @patch('alisa.services.health.Path')
    def test_get_cpu_temperature_thermal_zone(self, mock_path):
        """Test CPU temperature from thermal zone."""
        mock_file = Mock()
        mock_file.exists.return_value = True
        mock_file.read_text.return_value = "45123\n"  # 45.123°C
        mock_path.return_value = mock_file
        
        temp = get_cpu_temperature()
        assert temp == 45.1
    
    @patch('alisa.services.health.Path')
    @patch('subprocess.run')
    def test_get_cpu_temperature_vcgencmd(self, mock_run, mock_path):
        """Test CPU temperature from vcgencmd."""
        # Thermal zone not available
        mock_file = Mock()
        mock_file.exists.return_value = False
        mock_path.return_value = mock_file
        
        # vcgencmd available
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "temp=47.2'C\n"
        mock_run.return_value = mock_result
        
        temp = get_cpu_temperature()
        assert temp == 47.2
    
    @patch('alisa.services.health.Path')
    @patch('subprocess.run')
    def test_get_cpu_temperature_fallback(self, mock_run, mock_path):
        """Test CPU temperature fallback when no methods work."""
        # Thermal zone not available
        mock_file = Mock()
        mock_file.exists.return_value = False
        mock_path.return_value = mock_file
        
        # vcgencmd fails
        mock_run.side_effect = Exception("Command not found")
        
        temp = get_cpu_temperature()
        assert temp == 0.0
    
    @patch('alisa.services.health.get_system_stats')
    def test_format_system_status(self, mock_stats):
        """Test system status formatting."""
        mock_stats.return_value = {
            "cpu_percent": 25.5,
            "memory_used_mb": 1024,
            "memory_total_mb": 4096,
            "memory_percent": 25.0,
            "disk_free_gb": 54,
            "disk_percent": 15.6,
            "temperature_c": 42.5,
            "load_avg_1m": 0.5,
            "load_avg_5m": 0.7,
            "load_avg_15m": 0.9,
            "swap_used_mb": 128,
            "swap_total_mb": 1024,
            "swap_percent": 12.5
        }
        
        status = format_system_status()
        
        assert "CPU: 25.5%" in status
        assert "RAM: 1024MB / 4096MB (25.0%)" in status
        assert "54GB bo'sh" in status
        assert "Swap: 128MB / 1024MB (12.5%)" in status
        assert "42.5°C" in status
        assert "0.5 / 0.7 / 0.9" in status
    
    @patch('alisa.services.health.get_system_stats')
    def test_format_system_status_no_data(self, mock_stats):
        """Test system status formatting with no data."""
        mock_stats.return_value = {}
        
        status = format_system_status()
        assert "ma'lumotlari olinmadi" in status
    
    @patch('alisa.services.health.get_system_stats')
    def test_is_system_healthy_good(self, mock_stats):
        """Test system health check with good values."""
        mock_stats.return_value = {
            "cpu_percent": 25.0,
            "memory_percent": 50.0,
            "temperature_c": 45.0,
            "disk_percent": 60.0,
            "swap_percent": 10.0
        }
        
        assert is_system_healthy() is True
    
    @patch('alisa.services.health.get_system_stats')
    def test_is_system_healthy_high_cpu(self, mock_stats):
        """Test system health check with high CPU."""
        mock_stats.return_value = {
            "cpu_percent": 95.0,
            "memory_percent": 50.0,
            "temperature_c": 45.0,
            "disk_percent": 60.0,
            "swap_percent": 10.0
        }
        
        assert is_system_healthy() is False
    
    @patch('alisa.services.health.get_system_stats')
    def test_is_system_healthy_high_memory(self, mock_stats):
        """Test system health check with high memory."""
        mock_stats.return_value = {
            "cpu_percent": 25.0,
            "memory_percent": 90.0,
            "temperature_c": 45.0,
            "disk_percent": 60.0,
            "swap_percent": 10.0
        }
        
        assert is_system_healthy() is False
    
    @patch('alisa.services.health.get_system_stats')
    def test_is_system_healthy_high_temp(self, mock_stats):
        """Test system health check with high temperature."""
        mock_stats.return_value = {
            "cpu_percent": 25.0,
            "memory_percent": 50.0,
            "temperature_c": 85.0,
            "disk_percent": 60.0,
            "swap_percent": 10.0
        }
        
        assert is_system_healthy() is False
    
    @patch('alisa.services.health.get_system_stats')
    def test_is_system_healthy_high_swap(self, mock_stats):
        """Test system health check with high swap usage."""
        mock_stats.return_value = {
            "cpu_percent": 25.0,
            "memory_percent": 50.0,
            "temperature_c": 45.0,
            "disk_percent": 60.0,
            "swap_percent": 60.0  # High swap usage
        }
        
        assert is_system_healthy() is False
    
    @patch('alisa.services.health.get_system_stats')
    def test_is_system_healthy_no_data(self, mock_stats):
        """Test system health check with no data."""
        mock_stats.return_value = {}
        
        assert is_system_healthy() is False

    @patch('alisa.services.health.psutil.virtual_memory')
    @patch('alisa.services.health.psutil.swap_memory')
    def test_check_memory_pressure_normal(self, mock_swap, mock_memory):
        """Test memory pressure check - normal level."""
        mock_mem = Mock()
        mock_mem.available = 2 * 1024 * 1024 * 1024  # 2GB available
        mock_mem.percent = 50.0
        mock_memory.return_value = mock_mem
        
        mock_swap_mem = Mock()
        mock_swap_mem.percent = 10.0  # Low swap usage
        mock_swap.return_value = mock_swap_mem
        
        from alisa.services.health import check_memory_pressure
        result = check_memory_pressure()
        
        assert result["pressure_level"] == "normal"
        assert result["swap_percent"] == 10.0
        assert result["available_mb"] == 2048.0
        assert result["memory_percent"] == 50.0
        assert len(result["suggestions"]) == 0

    @patch('alisa.services.health.psutil.virtual_memory')
    @patch('alisa.services.health.psutil.swap_memory')
    def test_check_memory_pressure_critical(self, mock_swap, mock_memory):
        """Test memory pressure check - critical level."""
        mock_mem = Mock()
        mock_mem.available = 100 * 1024 * 1024  # 100MB available
        mock_mem.percent = 95.0
        mock_memory.return_value = mock_mem
        
        mock_swap_mem = Mock()
        mock_swap_mem.percent = 15.0
        mock_swap.return_value = mock_swap_mem
        
        from alisa.services.health import check_memory_pressure
        result = check_memory_pressure()
        
        assert result["pressure_level"] == "critical"
        assert result["available_mb"] == 100.0
        assert result["memory_percent"] == 95.0
        assert result["swap_percent"] == 15.0
        assert "Consider restarting Alisa" in result["suggestions"][0]

    @patch('alisa.services.health.psutil.virtual_memory')
    @patch('alisa.services.health.psutil.swap_memory')
    def test_check_memory_pressure_high_swap(self, mock_swap, mock_memory):
        """Test memory pressure check - high swap usage."""
        mock_mem = Mock()
        mock_mem.available = 1024 * 1024 * 1024  # 1GB available
        mock_mem.percent = 75.0
        mock_memory.return_value = mock_mem
        
        mock_swap_mem = Mock()
        mock_swap_mem.percent = 30.0  # High swap usage
        mock_swap.return_value = mock_swap_mem
        
        from alisa.services.health import check_memory_pressure
        result = check_memory_pressure()
        
        assert result["pressure_level"] == "high"
        assert result["swap_percent"] == 30.0
        assert "High swap usage detected" in result["suggestions"][0]
        assert "SD card" in result["suggestions"][0]

    @patch('alisa.services.health.psutil.virtual_memory')
    @patch('alisa.services.health.psutil.swap_memory')
    def test_check_memory_pressure_error(self, mock_swap, mock_memory):
        """Test memory pressure check with error."""
        mock_memory.side_effect = Exception("Memory error")
        mock_swap.side_effect = Exception("Swap error")
        
        from alisa.services.health import check_memory_pressure
        result = check_memory_pressure()
        
        assert result["pressure_level"] == "unknown"
        assert result["available_mb"] == 0
        assert result["swap_percent"] == 0
        assert "Unable to check memory pressure" in result["suggestions"]

    @patch('alisa.services.health.psutil.boot_time')
    @patch('alisa.services.health.time.time')
    def test_get_system_stats_includes_uptime(self, mock_time, mock_boot_time):
        """Test that system stats includes uptime information."""
        # Mock boot time (1 hour ago)
        mock_boot_time.return_value = 1000000
        mock_time.return_value = 1003600  # 1 hour later
        
        with patch('alisa.services.health.psutil.cpu_percent', return_value=10), \
             patch('alisa.services.health.psutil.virtual_memory') as mock_mem, \
             patch('alisa.services.health.psutil.disk_usage') as mock_disk, \
             patch('alisa.services.health.psutil.getloadavg', return_value=(0.1, 0.2, 0.3)), \
             patch('alisa.services.health.psutil.swap_memory') as mock_swap, \
             patch('alisa.services.health.get_cpu_temperature', return_value=45.0):
            
            # Setup mocks
            mock_mem.return_value = Mock(percent=50, used=1024*1024*1024, total=2048*1024*1024)
            mock_disk.return_value = Mock(used=10*1024*1024*1024, total=64*1024*1024*1024, free=54*1024*1024*1024)
            mock_swap.return_value = Mock(percent=10, used=100*1024*1024, total=1024*1024*1024)
            
            stats = get_system_stats()
            
            assert "uptime_hours" in stats
            assert isinstance(stats["uptime_hours"], (int, float))
            assert stats["uptime_hours"] == 1.0  # 1 hour uptime
