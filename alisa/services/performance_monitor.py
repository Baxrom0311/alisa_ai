"""Performance monitoring for Alisa AI Assistant."""

import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Dict, List, Optional
import structlog

logger = structlog.get_logger()


@dataclass
class PerformanceMetric:
    """Performance metric data."""
    name: str
    duration_ms: float
    timestamp: float
    memory_delta_mb: Optional[float] = None
    success: bool = True
    error: Optional[str] = None


class PerformanceMonitor:
    """Lightweight performance monitoring for Pi deployment."""
    
    def __init__(self, max_metrics: int = 1000):
        self.max_metrics = max_metrics
        self.metrics: List[PerformanceMetric] = []
        self._lock = asyncio.Lock()
    
    async def record_metric(self, metric: PerformanceMetric):
        """Record a performance metric."""
        async with self._lock:
            self.metrics.append(metric)
            
            # Keep only recent metrics to prevent memory growth
            if len(self.metrics) > self.max_metrics:
                self.metrics = self.metrics[-self.max_metrics:]
    
    @asynccontextmanager
    async def measure(self, operation_name: str, track_memory: bool = False):
        """Context manager to measure operation performance."""
        start_time = time.perf_counter()
        start_memory = None
        
        if track_memory:
            try:
                import psutil
                process = psutil.Process()
                start_memory = process.memory_info().rss / 1024 / 1024  # MB
            except ImportError:
                pass
        
        error = None
        success = True
        
        try:
            yield
        except Exception as e:
            error = str(e)
            success = False
            raise
        finally:
            end_time = time.perf_counter()
            duration_ms = (end_time - start_time) * 1000
            
            memory_delta = None
            if track_memory and start_memory is not None:
                try:
                    import psutil
                    process = psutil.Process()
                    end_memory = process.memory_info().rss / 1024 / 1024  # MB
                    memory_delta = end_memory - start_memory
                except ImportError:
                    pass
            
            metric = PerformanceMetric(
                name=operation_name,
                duration_ms=duration_ms,
                timestamp=time.time(),
                memory_delta_mb=memory_delta,
                success=success,
                error=error
            )
            
            await self.record_metric(metric)
            
            # Log slow operations
            if duration_ms > 5000:  # > 5 seconds
                logger.warning("slow_operation", 
                             operation=operation_name, 
                             duration_ms=duration_ms,
                             memory_delta_mb=memory_delta)
    
    async def get_summary(self, last_minutes: int = 60) -> Dict:
        """Get performance summary for the last N minutes."""
        async with self._lock:
            cutoff_time = time.time() - (last_minutes * 60)
            recent_metrics = [m for m in self.metrics if m.timestamp >= cutoff_time]
            
            if not recent_metrics:
                return {"total_operations": 0}
            
            # Group by operation name
            by_operation = {}
            for metric in recent_metrics:
                if metric.name not in by_operation:
                    by_operation[metric.name] = []
                by_operation[metric.name].append(metric)
            
            summary = {
                "total_operations": len(recent_metrics),
                "time_window_minutes": last_minutes,
                "operations": {}
            }
            
            for op_name, op_metrics in by_operation.items():
                durations = [m.duration_ms for m in op_metrics]
                successes = sum(1 for m in op_metrics if m.success)
                
                summary["operations"][op_name] = {
                    "count": len(op_metrics),
                    "success_rate": successes / len(op_metrics),
                    "avg_duration_ms": sum(durations) / len(durations),
                    "min_duration_ms": min(durations),
                    "max_duration_ms": max(durations),
                    "total_duration_ms": sum(durations)
                }
                
                # Add memory stats if available
                memory_deltas = [m.memory_delta_mb for m in op_metrics if m.memory_delta_mb is not None]
                if memory_deltas:
                    summary["operations"][op_name]["avg_memory_delta_mb"] = sum(memory_deltas) / len(memory_deltas)
            
            return summary
    
    async def get_slow_operations(self, threshold_ms: float = 3000) -> List[PerformanceMetric]:
        """Get operations that took longer than threshold."""
        async with self._lock:
            return [m for m in self.metrics if m.duration_ms > threshold_ms]
    
    async def clear_metrics(self):
        """Clear all stored metrics."""
        async with self._lock:
            self.metrics.clear()


# Global performance monitor instance
_performance_monitor = None


def get_performance_monitor() -> PerformanceMonitor:
    """Get the global performance monitor instance."""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor()
    return _performance_monitor
