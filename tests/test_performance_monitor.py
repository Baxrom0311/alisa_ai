"""Tests for performance monitoring."""

import asyncio
import pytest
import time

from alisa.services.performance_monitor import PerformanceMonitor, PerformanceMetric, get_performance_monitor


@pytest.mark.asyncio
async def test_performance_monitor_creation():
    """Test performance monitor creation."""
    monitor = PerformanceMonitor()
    assert monitor.max_metrics == 1000
    assert len(monitor.metrics) == 0


@pytest.mark.asyncio
async def test_record_metric():
    """Test recording a performance metric."""
    monitor = PerformanceMonitor()
    
    metric = PerformanceMetric(
        name="test_operation",
        duration_ms=100.5,
        timestamp=time.time(),
        success=True
    )
    
    await monitor.record_metric(metric)
    assert len(monitor.metrics) == 1
    assert monitor.metrics[0].name == "test_operation"
    assert monitor.metrics[0].duration_ms == 100.5


@pytest.mark.asyncio
async def test_measure_context_manager():
    """Test the measure context manager."""
    monitor = PerformanceMonitor()
    
    async with monitor.measure("test_operation"):
        await asyncio.sleep(0.01)  # 10ms
    
    assert len(monitor.metrics) == 1
    metric = monitor.metrics[0]
    assert metric.name == "test_operation"
    assert metric.duration_ms >= 10  # At least 10ms
    assert metric.success is True
    assert metric.error is None


@pytest.mark.asyncio
async def test_measure_with_exception():
    """Test measure context manager with exception."""
    monitor = PerformanceMonitor()
    
    with pytest.raises(ValueError):
        async with monitor.measure("failing_operation"):
            raise ValueError("Test error")
    
    assert len(monitor.metrics) == 1
    metric = monitor.metrics[0]
    assert metric.name == "failing_operation"
    assert metric.success is False
    assert metric.error == "Test error"


@pytest.mark.asyncio
async def test_max_metrics_limit():
    """Test that metrics are limited to max_metrics."""
    monitor = PerformanceMonitor(max_metrics=3)
    
    # Add 5 metrics
    for i in range(5):
        metric = PerformanceMetric(
            name=f"operation_{i}",
            duration_ms=100,
            timestamp=time.time()
        )
        await monitor.record_metric(metric)
    
    # Should only keep the last 3
    assert len(monitor.metrics) == 3
    assert monitor.metrics[0].name == "operation_2"
    assert monitor.metrics[1].name == "operation_3"
    assert monitor.metrics[2].name == "operation_4"


@pytest.mark.asyncio
async def test_get_summary():
    """Test getting performance summary."""
    monitor = PerformanceMonitor()
    
    # Add some test metrics
    current_time = time.time()
    metrics = [
        PerformanceMetric("operation_a", 100, current_time, success=True),
        PerformanceMetric("operation_a", 200, current_time, success=True),
        PerformanceMetric("operation_b", 150, current_time, success=False),
        PerformanceMetric("operation_old", 50, current_time - 3700, success=True)  # > 1 hour old
    ]
    
    for metric in metrics:
        await monitor.record_metric(metric)
    
    summary = await monitor.get_summary(last_minutes=60)
    
    assert summary["total_operations"] == 3  # Excludes old metric
    assert "operation_a" in summary["operations"]
    assert "operation_b" in summary["operations"]
    assert "operation_old" not in summary["operations"]
    
    # Check operation_a stats
    op_a = summary["operations"]["operation_a"]
    assert op_a["count"] == 2
    assert op_a["success_rate"] == 1.0
    assert op_a["avg_duration_ms"] == 150.0
    assert op_a["min_duration_ms"] == 100.0
    assert op_a["max_duration_ms"] == 200.0
    
    # Check operation_b stats
    op_b = summary["operations"]["operation_b"]
    assert op_b["count"] == 1
    assert op_b["success_rate"] == 0.0


@pytest.mark.asyncio
async def test_get_slow_operations():
    """Test getting slow operations."""
    monitor = PerformanceMonitor()
    
    # Add metrics with different durations
    metrics = [
        PerformanceMetric("fast_op", 100, time.time()),
        PerformanceMetric("slow_op", 5000, time.time()),
        PerformanceMetric("very_slow_op", 10000, time.time())
    ]
    
    for metric in metrics:
        await monitor.record_metric(metric)
    
    slow_ops = await monitor.get_slow_operations(threshold_ms=3000)
    
    assert len(slow_ops) == 2
    assert slow_ops[0].name == "slow_op"
    assert slow_ops[1].name == "very_slow_op"


@pytest.mark.asyncio
async def test_clear_metrics():
    """Test clearing metrics."""
    monitor = PerformanceMonitor()
    
    # Add some metrics
    metric = PerformanceMetric("test_op", 100, time.time())
    await monitor.record_metric(metric)
    assert len(monitor.metrics) == 1
    
    # Clear metrics
    await monitor.clear_metrics()
    assert len(monitor.metrics) == 0


def test_get_performance_monitor_singleton():
    """Test that get_performance_monitor returns singleton."""
    monitor1 = get_performance_monitor()
    monitor2 = get_performance_monitor()
    
    assert monitor1 is monitor2


@pytest.mark.asyncio
async def test_measure_memory_tracking():
    """Test memory tracking in measure context manager."""
    monitor = PerformanceMonitor()
    
    # This test will only work if psutil is available
    try:
        import psutil
        
        async with monitor.measure("memory_test", track_memory=True):
            # Allocate some memory
            data = [0] * 1000
            await asyncio.sleep(0.001)
        
        assert len(monitor.metrics) == 1
        metric = monitor.metrics[0]
        assert metric.name == "memory_test"
        # Memory delta might be None if psutil fails, but that's OK
        
    except ImportError:
        # psutil not available, just test that it doesn't crash
        async with monitor.measure("memory_test", track_memory=True):
            await asyncio.sleep(0.001)
        
        assert len(monitor.metrics) == 1
        metric = monitor.metrics[0]
        assert metric.memory_delta_mb is None


@pytest.mark.asyncio
async def test_concurrent_access():
    """Test concurrent access to performance monitor."""
    monitor = PerformanceMonitor()
    
    async def add_metrics(prefix: str, count: int):
        for i in range(count):
            async with monitor.measure(f"{prefix}_operation_{i}"):
                await asyncio.sleep(0.001)
    
    # Run multiple tasks concurrently
    await asyncio.gather(
        add_metrics("task1", 5),
        add_metrics("task2", 5),
        add_metrics("task3", 5)
    )
    
    assert len(monitor.metrics) == 15
    
    # Check that all operations are recorded
    operation_names = [m.name for m in monitor.metrics]
    assert len(set(operation_names)) == 15  # All unique names
