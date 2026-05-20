"""Performance profiler for monitoring Alisa operations on Raspberry Pi."""

import time
import asyncio
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from collections import defaultdict, deque
import structlog

logger = structlog.get_logger()


@dataclass
class PerformanceMetric:
    """Single performance measurement."""
    operation: str
    duration_ms: float
    timestamp: float
    memory_mb: Optional[float] = None
    cpu_percent: Optional[float] = None


class PerformanceProfiler:
    """Lightweight performance profiler for Pi optimization."""
    
    def __init__(self, max_metrics: int = 1000):
        self.max_metrics = max_metrics
        self.metrics: deque = deque(maxlen=max_metrics)
        self.operation_stats: Dict[str, List[float]] = defaultdict(list)
        self._enabled = True
        
    def enable(self):
        """Enable profiling."""
        self._enabled = True
        
    def disable(self):
        """Disable profiling."""
        self._enabled = False
        
    def record_metric(self, operation: str, duration_ms: float, 
                     memory_mb: Optional[float] = None, 
                     cpu_percent: Optional[float] = None):
        """Record a performance metric."""
        if not self._enabled:
            return
            
        metric = PerformanceMetric(
            operation=operation,
            duration_ms=duration_ms,
            timestamp=time.time(),
            memory_mb=memory_mb,
            cpu_percent=cpu_percent
        )
        
        self.metrics.append(metric)
        self.operation_stats[operation].append(duration_ms)
        
        # Keep only recent stats to prevent memory growth
        # Trim when we exceed 100 items, keep last 50
        if len(self.operation_stats[operation]) > 100:
            self.operation_stats[operation] = self.operation_stats[operation][-50:]
    
    def get_stats(self) -> Dict[str, Dict[str, float]]:
        """Get performance statistics."""
        stats = {}
        
        for operation, durations in self.operation_stats.items():
            if durations:
                stats[operation] = {
                    "avg_ms": sum(durations) / len(durations),
                    "min_ms": min(durations),
                    "max_ms": max(durations),
                    "count": len(durations)
                }
        
        return stats
    
    def get_slow_operations(self, threshold_ms: float = 1000) -> List[PerformanceMetric]:
        """Get operations that exceeded threshold."""
        return [m for m in self.metrics if m.duration_ms > threshold_ms]
    
    def clear(self):
        """Clear all metrics."""
        self.metrics.clear()
        self.operation_stats.clear()


class ProfiledOperation:
    """Context manager for profiling operations."""
    
    def __init__(self, profiler: PerformanceProfiler, operation: str):
        self.profiler = profiler
        self.operation = operation
        self.start_time = 0
        
    def __enter__(self):
        self.start_time = time.perf_counter()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.perf_counter() - self.start_time) * 1000
        self.profiler.record_metric(self.operation, duration_ms)


class AsyncProfiledOperation:
    """Async context manager for profiling operations."""
    
    def __init__(self, profiler: PerformanceProfiler, operation: str):
        self.profiler = profiler
        self.operation = operation
        self.start_time = 0
        
    async def __aenter__(self):
        self.start_time = time.perf_counter()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.perf_counter() - self.start_time) * 1000
        self.profiler.record_metric(self.operation, duration_ms)


# Global profiler instance
_profiler = PerformanceProfiler()


def get_profiler() -> PerformanceProfiler:
    """Get the global profiler instance."""
    return _profiler


def profile_operation(operation: str):
    """Decorator for profiling sync functions."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            with ProfiledOperation(_profiler, operation):
                return func(*args, **kwargs)
        return wrapper
    return decorator


def profile_async_operation(operation: str):
    """Decorator for profiling async functions."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            async with AsyncProfiledOperation(_profiler, operation):
                return await func(*args, **kwargs)
        return wrapper
    return decorator
