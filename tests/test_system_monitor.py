"""Tests for system monitoring utility."""

import asyncio
import time
import pytest
from unittest.mock import Mock, patch, AsyncMock

from alisa.services.system_monitor import (
    SystemMonitor, SystemSnapshot, MonitoringAlert, get_system_monitor
)


class TestSystemSnapshot:
    """Test SystemSnapshot dataclass."""
    
    def test_snapshot_creation(self):
        """Test creating a system snapshot."""
        snapshot = SystemSnapshot(
            timestamp=time.time(),
            cpu_percent=25.5,
            memory_percent=60.0,
            memory_used_mb=2048,
            memory_total_mb=4096,
            disk_percent=45.0,
            disk_free_gb=100,
            temperature_c=45.5,
            load_avg_1m=1.5,
            uptime_hours=24.5,
            active_llm_providers=3,
            llm_requests_total=150
        )
        
        assert snapshot.cpu_percent == 25.5
        assert snapshot.memory_percent == 60.0
        assert snapshot.active_llm_providers == 3


class TestMonitoringAlert:
    """Test MonitoringAlert dataclass."""
    
    def test_alert_creation(self):
        """Test creating a monitoring alert."""
        alert = MonitoringAlert(
            timestamp=time.time(),
            level="WARNING",
            component="CPU",
            message="CPU usage high: 85.0%",
            value=85.0,
            threshold=80.0
        )
        
        assert alert.level == "WARNING"
        assert alert.component == "CPU"
        assert alert.value == 85.0


class TestSystemMonitor:
    """Test SystemMonitor class."""
    
    @pytest.fixture
    def monitor(self):
        """Create a system monitor instance."""
        return SystemMonitor(history_size=10)
    
    @pytest.fixture
    def mock_stats(self):
        """Mock system stats."""
        return {
            'cpu_percent': 25.0,
            'memory_percent': 60.0,
            'memory_used_mb': 2048,
            'memory_total_mb': 4096,
            'disk_percent': 45.0,
            'disk_free_gb': 100,
            'temperature_c': 45.0,
            'load_avg_1m': 1.5,
            'uptime_hours': 24.0
        }
    
    @pytest.fixture
    def mock_llm_status(self):
        """Mock LLM manager status."""
        return {
            'active_providers': 2,
            'providers': {
                'openai': {'requests': 50},
                'gemini': {'requests': 30}
            }
        }
    
    def test_monitor_initialization(self, monitor):
        """Test monitor initialization."""
        assert monitor.history_size == 10
        assert len(monitor.snapshots) == 0
        assert len(monitor.alerts) == 0
        assert not monitor.is_monitoring
        assert len(monitor.alert_callbacks) == 0
    
    def test_alert_callback_management(self, monitor):
        """Test adding and removing alert callbacks."""
        callback1 = Mock()
        callback2 = Mock()
        
        monitor.add_alert_callback(callback1)
        monitor.add_alert_callback(callback2)
        assert len(monitor.alert_callbacks) == 2
        
        monitor.remove_alert_callback(callback1)
        assert len(monitor.alert_callbacks) == 1
        assert callback2 in monitor.alert_callbacks
    
    @patch('alisa.services.system_monitor.get_system_stats')
    @patch('alisa.services.system_monitor.get_llm_manager')
    @pytest.mark.asyncio
    async def test_take_snapshot(self, mock_llm_manager, mock_get_stats, 
                               monitor, mock_stats, mock_llm_status):
        """Test taking a system snapshot."""
        mock_get_stats.return_value = mock_stats
        mock_manager = Mock()
        mock_manager.get_provider_status.return_value = mock_llm_status
        mock_llm_manager.return_value = mock_manager
        
        snapshot = await monitor.take_snapshot()
        
        assert isinstance(snapshot, SystemSnapshot)
        assert snapshot.cpu_percent == 25.0
        assert snapshot.memory_percent == 60.0
        assert snapshot.active_llm_providers == 2
        assert snapshot.llm_requests_total == 80  # 50 + 30
        
        # Check history
        assert len(monitor.snapshots) == 1
        assert monitor.snapshots[0] == snapshot
    
    @patch('alisa.services.system_monitor.get_system_stats')
    @patch('alisa.services.system_monitor.get_llm_manager')
    @pytest.mark.asyncio
    async def test_snapshot_history_limit(self, mock_llm_manager, mock_get_stats, 
                                        monitor, mock_stats, mock_llm_status):
        """Test snapshot history size limit."""
        mock_get_stats.return_value = mock_stats
        mock_manager = Mock()
        mock_manager.get_provider_status.return_value = mock_llm_status
        mock_llm_manager.return_value = mock_manager
        
        # Take more snapshots than history size
        for i in range(15):
            await monitor.take_snapshot()
        
        # Should only keep last 10
        assert len(monitor.snapshots) == 10
    
    @patch('alisa.services.system_monitor.get_system_stats')
    @patch('alisa.services.system_monitor.get_llm_manager')
    @pytest.mark.asyncio
    async def test_cpu_alerts(self, mock_llm_manager, mock_get_stats, 
                            monitor, mock_stats, mock_llm_status):
        """Test CPU usage alerts."""
        mock_manager = Mock()
        mock_manager.get_provider_status.return_value = mock_llm_status
        mock_llm_manager.return_value = mock_manager
        
        # Test warning alert
        mock_stats['cpu_percent'] = 85.0
        mock_get_stats.return_value = mock_stats
        
        await monitor.take_snapshot()
        
        assert len(monitor.alerts) == 1
        alert = monitor.alerts[0]
        assert alert.level == "WARNING"
        assert alert.component == "CPU"
        assert alert.value == 85.0
        
        # Test critical alert
        mock_stats['cpu_percent'] = 98.0
        mock_get_stats.return_value = mock_stats
        
        await monitor.take_snapshot()
        
        assert len(monitor.alerts) == 2
        critical_alert = monitor.alerts[1]
        assert critical_alert.level == "CRITICAL"
        assert critical_alert.component == "CPU"
        assert critical_alert.value == 98.0
    
    @patch('alisa.services.system_monitor.get_system_stats')
    @patch('alisa.services.system_monitor.get_llm_manager')
    @pytest.mark.asyncio
    async def test_memory_alerts(self, mock_llm_manager, mock_get_stats, 
                               monitor, mock_stats, mock_llm_status):
        """Test memory usage alerts."""
        mock_manager = Mock()
        mock_manager.get_provider_status.return_value = mock_llm_status
        mock_llm_manager.return_value = mock_manager
        
        # Test memory warning
        mock_stats['memory_percent'] = 90.0
        mock_get_stats.return_value = mock_stats
        
        await monitor.take_snapshot()
        
        assert len(monitor.alerts) == 1
        alert = monitor.alerts[0]
        assert alert.level == "WARNING"
        assert alert.component == "Memory"
        assert alert.value == 90.0
    
    @patch('alisa.services.system_monitor.get_system_stats')
    @patch('alisa.services.system_monitor.get_llm_manager')
    @pytest.mark.asyncio
    async def test_temperature_alerts(self, mock_llm_manager, mock_get_stats, 
                                    monitor, mock_stats, mock_llm_status):
        """Test temperature alerts."""
        mock_manager = Mock()
        mock_manager.get_provider_status.return_value = mock_llm_status
        mock_llm_manager.return_value = mock_manager
        
        # Test temperature warning
        mock_stats['temperature_c'] = 75.0
        mock_get_stats.return_value = mock_stats
        
        await monitor.take_snapshot()
        
        assert len(monitor.alerts) == 1
        alert = monitor.alerts[0]
        assert alert.level == "WARNING"
        assert alert.component == "Temperature"
        assert alert.value == 75.0
    
    @patch('alisa.services.system_monitor.get_system_stats')
    @patch('alisa.services.system_monitor.get_llm_manager')
    @pytest.mark.asyncio
    async def test_alert_callbacks(self, mock_llm_manager, mock_get_stats, 
                                 monitor, mock_stats, mock_llm_status):
        """Test alert callback notifications."""
        mock_manager = Mock()
        mock_manager.get_provider_status.return_value = mock_llm_status
        mock_llm_manager.return_value = mock_manager
        
        callback = Mock()
        monitor.add_alert_callback(callback)
        
        # Trigger alert
        mock_stats['cpu_percent'] = 85.0
        mock_get_stats.return_value = mock_stats
        
        await monitor.take_snapshot()
        
        # Check callback was called
        callback.assert_called_once()
        alert = callback.call_args[0][0]
        assert isinstance(alert, MonitoringAlert)
        assert alert.level == "WARNING"
    
    @pytest.mark.asyncio
    async def test_monitoring_lifecycle(self, monitor):
        """Test starting and stopping monitoring."""
        assert not monitor.is_monitoring
        
        # Start monitoring in background
        monitor_task = asyncio.create_task(monitor.start_monitoring(interval=0.1))
        
        # Wait a bit for monitoring to start
        await asyncio.sleep(0.05)
        assert monitor.is_monitoring
        
        # Stop monitoring
        monitor.stop_monitoring()
        
        # Wait for task to complete
        try:
            await asyncio.wait_for(monitor_task, timeout=1.0)
        except asyncio.TimeoutError:
            monitor_task.cancel()
        
        assert not monitor.is_monitoring
    
    @patch('alisa.services.system_monitor.get_system_stats')
    @patch('alisa.services.system_monitor.get_llm_manager')
    def test_current_status(self, mock_llm_manager, mock_get_stats, 
                          monitor, mock_stats, mock_llm_status):
        """Test getting current status."""
        # No data initially
        status = monitor.get_current_status()
        assert status['status'] == 'no_data'
        
        # Add a snapshot
        mock_get_stats.return_value = mock_stats
        mock_manager = Mock()
        mock_manager.get_provider_status.return_value = mock_llm_status
        mock_llm_manager.return_value = mock_manager
        
        # Use asyncio.run to handle async method
        asyncio.run(monitor.take_snapshot())
        
        status = monitor.get_current_status()
        assert status['status'] == 'stopped'
        assert 'latest_snapshot' in status
        assert status['history_size'] == 1
    
    @patch('alisa.services.system_monitor.get_system_stats')
    @patch('alisa.services.system_monitor.get_llm_manager')
    def test_performance_summary(self, mock_llm_manager, mock_get_stats, 
                               monitor, mock_stats, mock_llm_status):
        """Test performance summary."""
        mock_manager = Mock()
        mock_manager.get_provider_status.return_value = mock_llm_status
        mock_llm_manager.return_value = mock_manager
        
        # Insufficient data
        summary = monitor.get_performance_summary()
        assert summary['status'] == 'insufficient_data'
        
        # Add multiple snapshots
        for i in range(5):
            mock_stats['cpu_percent'] = 20.0 + i * 5
            mock_stats['memory_percent'] = 50.0 + i * 2
            mock_get_stats.return_value = mock_stats
            asyncio.run(monitor.take_snapshot())
        
        summary = monitor.get_performance_summary()
        assert 'avg_cpu' in summary
        assert 'max_cpu' in summary
        assert 'avg_memory' in summary
        assert summary['samples'] == 5
    
    def test_threshold_management(self, monitor):
        """Test setting alert thresholds."""
        # Set valid threshold
        monitor.set_threshold('cpu', 'warning', 75.0)
        assert monitor.thresholds['cpu_warning'] == 75.0
        
        # Invalid threshold should raise error
        with pytest.raises(ValueError):
            monitor.set_threshold('invalid', 'warning', 50.0)
    
    @patch('alisa.services.system_monitor.get_system_stats')
    @patch('alisa.services.system_monitor.get_llm_manager')
    def test_history_filtering(self, mock_llm_manager, mock_get_stats, 
                             monitor, mock_stats, mock_llm_status):
        """Test getting filtered history."""
        mock_manager = Mock()
        mock_manager.get_provider_status.return_value = mock_llm_status
        mock_llm_manager.return_value = mock_manager
        mock_get_stats.return_value = mock_stats
        
        # Add snapshots with different timestamps
        base_time = time.time()
        for i in range(5):
            with patch('time.time', return_value=base_time - (i * 60)):  # 1 minute apart
                asyncio.run(monitor.take_snapshot())
        
        # Get recent history (should get all 5)
        recent = monitor.get_history(minutes=10)
        assert len(recent) == 5
        
        # Get very recent history (should get fewer)
        very_recent = monitor.get_history(minutes=2)
        assert len(very_recent) <= 3
    
    @patch('alisa.services.system_monitor.get_system_stats')
    @patch('alisa.services.system_monitor.get_llm_manager')
    def test_alert_filtering(self, mock_llm_manager, mock_get_stats, 
                           monitor, mock_stats, mock_llm_status):
        """Test getting filtered alerts."""
        mock_manager = Mock()
        mock_manager.get_provider_status.return_value = mock_llm_status
        mock_llm_manager.return_value = mock_manager
        
        # Trigger alerts at different times
        base_time = time.time()
        for i in range(3):
            mock_stats['cpu_percent'] = 85.0  # Trigger warning
            mock_get_stats.return_value = mock_stats
            
            with patch('time.time', return_value=base_time - (i * 60)):
                asyncio.run(monitor.take_snapshot())
        
        # Get recent alerts
        recent_alerts = monitor.get_alerts(minutes=5)
        assert len(recent_alerts) >= 1  # At least one recent alert


class TestGlobalInstance:
    """Test global system monitor instance."""
    
    def test_get_system_monitor(self):
        """Test getting global system monitor instance."""
        monitor1 = get_system_monitor()
        monitor2 = get_system_monitor()
        
        # Should return same instance
        assert monitor1 is monitor2
        assert isinstance(monitor1, SystemMonitor)


class TestIntegration:
    """Integration tests for system monitor."""
    
    @pytest.mark.asyncio
    async def test_full_monitoring_cycle(self):
        """Test complete monitoring cycle."""
        monitor = SystemMonitor(history_size=5)
        
        # Mock alert callback
        alerts_received = []
        def alert_callback(alert):
            alerts_received.append(alert)
        
        monitor.add_alert_callback(alert_callback)
        
        # Mock system stats to trigger alerts
        with patch('alisa.services.system_monitor.get_system_stats') as mock_stats, \
             patch('alisa.services.system_monitor.get_llm_manager') as mock_llm:
            
            mock_stats.return_value = {
                'cpu_percent': 90.0,  # Should trigger warning
                'memory_percent': 60.0,
                'memory_used_mb': 2048,
                'memory_total_mb': 4096,
                'disk_percent': 45.0,
                'disk_free_gb': 100,
                'temperature_c': 45.0,
                'load_avg_1m': 1.5,
                'uptime_hours': 24.0
            }
            
            mock_manager = Mock()
            mock_manager.get_provider_status.return_value = {
                'active_providers': 1,
                'providers': {'openai': {'requests': 10}}
            }
            mock_llm.return_value = mock_manager
            
            # Take snapshot
            snapshot = await monitor.take_snapshot()
            
            # Verify snapshot
            assert snapshot.cpu_percent == 90.0
            assert len(monitor.snapshots) == 1
            
            # Verify alert was triggered and callback called
            assert len(monitor.alerts) == 1
            assert len(alerts_received) == 1
            assert alerts_received[0].level == "WARNING"
            assert alerts_received[0].component == "CPU"
            
            # Get status
            status = monitor.get_current_status()
            assert status['status'] == 'stopped'
            assert status['warning_alerts'] == 1
            assert status['critical_alerts'] == 0
