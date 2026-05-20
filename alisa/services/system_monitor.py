"""Real-time system monitoring utility for Alisa AI Assistant."""

import asyncio
import time
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta

import structlog

from alisa.services.health import get_system_stats
from alisa.brain.llm_manager import get_llm_manager

logger = structlog.get_logger()


@dataclass
class SystemSnapshot:
    """System state snapshot."""
    timestamp: float
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_total_mb: float
    disk_percent: float
    disk_free_gb: float
    temperature_c: float
    load_avg_1m: float
    uptime_hours: float
    active_llm_providers: int
    llm_requests_total: int


@dataclass
class MonitoringAlert:
    """System monitoring alert."""
    timestamp: float
    level: str  # INFO, WARNING, CRITICAL
    component: str
    message: str
    value: float
    threshold: float


class SystemMonitor:
    """Real-time system monitoring with alerts and history."""
    
    def __init__(self, history_size: int = 100):
        self.history_size = history_size
        self.snapshots: List[SystemSnapshot] = []
        self.alerts: List[MonitoringAlert] = []
        self.alert_callbacks: List[Callable[[MonitoringAlert], None]] = []
        self.is_monitoring = False
        self.monitor_task: Optional[asyncio.Task] = None
        
        # Alert thresholds
        self.thresholds = {
            'cpu_warning': 80.0,
            'cpu_critical': 95.0,
            'memory_warning': 85.0,
            'memory_critical': 95.0,
            'disk_warning': 90.0,
            'disk_critical': 95.0,
            'temperature_warning': 70.0,
            'temperature_critical': 80.0,
        }
    
    def add_alert_callback(self, callback: Callable[[MonitoringAlert], None]):
        """Add callback for alert notifications."""
        self.alert_callbacks.append(callback)
    
    def remove_alert_callback(self, callback: Callable[[MonitoringAlert], None]):
        """Remove alert callback."""
        if callback in self.alert_callbacks:
            self.alert_callbacks.remove(callback)
    
    async def take_snapshot(self) -> SystemSnapshot:
        """Take a system snapshot."""
        try:
            stats = get_system_stats()
            llm_manager = get_llm_manager()
            llm_status = llm_manager.get_provider_status()
            
            snapshot = SystemSnapshot(
                timestamp=time.time(),
                cpu_percent=stats.get('cpu_percent', 0.0),
                memory_percent=stats.get('memory_percent', 0.0),
                memory_used_mb=stats.get('memory_used_mb', 0.0),
                memory_total_mb=stats.get('memory_total_mb', 0.0),
                disk_percent=stats.get('disk_percent', 0.0),
                disk_free_gb=stats.get('disk_free_gb', 0.0),
                temperature_c=stats.get('temperature_c', 0.0),
                load_avg_1m=stats.get('load_avg_1m', 0.0),
                uptime_hours=stats.get('uptime_hours', 0.0),
                active_llm_providers=llm_status.get('active_providers', 0),
                llm_requests_total=sum(
                    provider.get('requests', 0) 
                    for provider in llm_status.get('providers', {}).values()
                )
            )
            
            # Add to history
            self.snapshots.append(snapshot)
            if len(self.snapshots) > self.history_size:
                self.snapshots.pop(0)
            
            # Check for alerts
            await self._check_alerts(snapshot)
            
            return snapshot
            
        except Exception as e:
            logger.error("snapshot_failed", error=str(e))
            raise
    
    async def _check_alerts(self, snapshot: SystemSnapshot):
        """Check snapshot for alert conditions."""
        current_time = snapshot.timestamp
        
        # CPU alerts
        if snapshot.cpu_percent >= self.thresholds['cpu_critical']:
            await self._create_alert(
                'CRITICAL', 'CPU', 
                f'CPU usage critical: {snapshot.cpu_percent:.1f}%',
                snapshot.cpu_percent, self.thresholds['cpu_critical']
            )
        elif snapshot.cpu_percent >= self.thresholds['cpu_warning']:
            await self._create_alert(
                'WARNING', 'CPU',
                f'CPU usage high: {snapshot.cpu_percent:.1f}%',
                snapshot.cpu_percent, self.thresholds['cpu_warning']
            )
        
        # Memory alerts
        if snapshot.memory_percent >= self.thresholds['memory_critical']:
            await self._create_alert(
                'CRITICAL', 'Memory',
                f'Memory usage critical: {snapshot.memory_percent:.1f}%',
                snapshot.memory_percent, self.thresholds['memory_critical']
            )
        elif snapshot.memory_percent >= self.thresholds['memory_warning']:
            await self._create_alert(
                'WARNING', 'Memory',
                f'Memory usage high: {snapshot.memory_percent:.1f}%',
                snapshot.memory_percent, self.thresholds['memory_warning']
            )
        
        # Disk alerts
        if snapshot.disk_percent >= self.thresholds['disk_critical']:
            await self._create_alert(
                'CRITICAL', 'Disk',
                f'Disk usage critical: {snapshot.disk_percent:.1f}%',
                snapshot.disk_percent, self.thresholds['disk_critical']
            )
        elif snapshot.disk_percent >= self.thresholds['disk_warning']:
            await self._create_alert(
                'WARNING', 'Disk',
                f'Disk usage high: {snapshot.disk_percent:.1f}%',
                snapshot.disk_percent, self.thresholds['disk_warning']
            )
        
        # Temperature alerts (if available)
        if snapshot.temperature_c > 0:
            if snapshot.temperature_c >= self.thresholds['temperature_critical']:
                await self._create_alert(
                    'CRITICAL', 'Temperature',
                    f'Temperature critical: {snapshot.temperature_c:.1f}°C',
                    snapshot.temperature_c, self.thresholds['temperature_critical']
                )
            elif snapshot.temperature_c >= self.thresholds['temperature_warning']:
                await self._create_alert(
                    'WARNING', 'Temperature',
                    f'Temperature high: {snapshot.temperature_c:.1f}°C',
                    snapshot.temperature_c, self.thresholds['temperature_warning']
                )
    
    async def _create_alert(self, level: str, component: str, message: str, 
                          value: float, threshold: float):
        """Create and process an alert."""
        alert = MonitoringAlert(
            timestamp=time.time(),
            level=level,
            component=component,
            message=message,
            value=value,
            threshold=threshold
        )
        
        # Add to alerts history
        self.alerts.append(alert)
        if len(self.alerts) > self.history_size:
            self.alerts.pop(0)
        
        # Log alert
        if level == 'CRITICAL':
            logger.critical("system_alert", 
                          component=component, message=message, 
                          value=value, threshold=threshold)
        else:
            logger.warning("system_alert", 
                          component=component, message=message, 
                          value=value, threshold=threshold)
        
        # Notify callbacks
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error("alert_callback_failed", error=str(e))
    
    async def start_monitoring(self, interval: float = 5.0):
        """Start continuous monitoring."""
        if self.is_monitoring:
            logger.warning("monitoring_already_running")
            return
        
        self.is_monitoring = True
        logger.info("monitoring_started", interval=interval)
        
        try:
            while self.is_monitoring:
                await self.take_snapshot()
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("monitoring_cancelled")
        except Exception as e:
            logger.error("monitoring_error", error=str(e))
        finally:
            self.is_monitoring = False
            logger.info("monitoring_stopped")
    
    def stop_monitoring(self):
        """Stop continuous monitoring."""
        self.is_monitoring = False
        if self.monitor_task and not self.monitor_task.done():
            self.monitor_task.cancel()
    
    def get_current_status(self) -> Dict:
        """Get current system status."""
        if not self.snapshots:
            return {'status': 'no_data'}
        
        latest = self.snapshots[-1]
        recent_alerts = [
            alert for alert in self.alerts 
            if alert.timestamp > time.time() - 300  # Last 5 minutes
        ]
        
        return {
            'status': 'monitoring' if self.is_monitoring else 'stopped',
            'latest_snapshot': asdict(latest),
            'recent_alerts': len(recent_alerts),
            'critical_alerts': len([a for a in recent_alerts if a.level == 'CRITICAL']),
            'warning_alerts': len([a for a in recent_alerts if a.level == 'WARNING']),
            'history_size': len(self.snapshots),
            'uptime': latest.uptime_hours
        }
    
    def get_history(self, minutes: int = 60) -> List[SystemSnapshot]:
        """Get system history for the last N minutes."""
        cutoff_time = time.time() - (minutes * 60)
        return [
            snapshot for snapshot in self.snapshots 
            if snapshot.timestamp >= cutoff_time
        ]
    
    def get_alerts(self, minutes: int = 60) -> List[MonitoringAlert]:
        """Get alerts for the last N minutes."""
        cutoff_time = time.time() - (minutes * 60)
        return [
            alert for alert in self.alerts 
            if alert.timestamp >= cutoff_time
        ]
    
    def get_performance_summary(self) -> Dict:
        """Get performance summary from recent history."""
        if len(self.snapshots) < 2:
            return {'status': 'insufficient_data'}
        
        recent = self.snapshots[-10:]  # Last 10 snapshots
        
        return {
            'avg_cpu': sum(s.cpu_percent for s in recent) / len(recent),
            'max_cpu': max(s.cpu_percent for s in recent),
            'avg_memory': sum(s.memory_percent for s in recent) / len(recent),
            'max_memory': max(s.memory_percent for s in recent),
            'avg_temperature': sum(s.temperature_c for s in recent) / len(recent) if any(s.temperature_c > 0 for s in recent) else 0,
            'max_temperature': max(s.temperature_c for s in recent),
            'disk_usage': recent[-1].disk_percent,
            'disk_free_gb': recent[-1].disk_free_gb,
            'active_providers': recent[-1].active_llm_providers,
            'total_requests': recent[-1].llm_requests_total,
            'samples': len(recent)
        }
    
    def set_threshold(self, metric: str, level: str, value: float):
        """Set alert threshold."""
        key = f"{metric}_{level}"
        if key in self.thresholds:
            self.thresholds[key] = value
            logger.info("threshold_updated", metric=metric, level=level, value=value)
        else:
            raise ValueError(f"Unknown threshold: {key}")


# Global instance
_system_monitor: Optional[SystemMonitor] = None


def get_system_monitor() -> SystemMonitor:
    """Get global system monitor instance."""
    global _system_monitor
    if _system_monitor is None:
        _system_monitor = SystemMonitor()
    return _system_monitor
