"""Tests for performance profiler."""

import asyncio
import time
import pytest
from unittest.mock import patch

from alisa.services.profiler import (
    PerformanceProfiler, ProfiledOperation, AsyncProfiledOperation,
    get_profiler, profile_operation, profile_async_operation
)


class TestPerformanceProfiler:
    """Test performance profiler functionality."""
    
    def test_init(self):
        """Test profiler initialization."""
        profiler = PerformanceProfiler(max_metrics=500)
        assert profiler.max_metrics == 500
        assert len(profiler.metrics) == 0
        assert len(profiler.operation_stats) == 0
        assert profiler._enabled is True
    
    def test_enable_disable(self):
        """Test enabling/disabling profiler."""
        profiler = PerformanceProfiler()
        
        profiler.disable()
        assert profiler._enabled is False
        
        profiler.enable()
        assert profiler._enabled is True
    
    def test_record_metric(self):
        """Test recording metrics."""
        profiler = PerformanceProfiler()
        
        profiler.record_metric("test_op", 100.5, memory_mb=512.0, cpu_percent=25.0)
        
        assert len(profiler.metrics) == 1
        metric = profiler.metrics[0]
        assert metric.operation == "test_op"
        assert metric.duration_ms == 100.5
        assert metric.memory_mb == 512.0
        assert metric.cpu_percent == 25.0
        assert metric.timestamp > 0
    
    def test_record_metric_disabled(self):
        """Test that disabled profiler doesn't record."""
        profiler = PerformanceProfiler()
        profiler.disable()
        
        profiler.record_metric("test_op", 100.5)
        
        assert len(profiler.metrics) == 0
        assert len(profiler.operation_stats) == 0
    
    def test_get_stats(self):
        """Test getting performance statistics."""
        profiler = PerformanceProfiler()
        
        # Record multiple metrics for same operation
        profiler.record_metric("test_op", 100.0)
        profiler.record_metric("test_op", 200.0)
        profiler.record_metric("test_op", 150.0)
        profiler.record_metric("other_op", 50.0)
        
        stats = profiler.get_stats()
        
        assert "test_op" in stats
        assert "other_op" in stats
        
        test_stats = stats["test_op"]
        assert test_stats["avg_ms"] == 150.0  # (100+200+150)/3
        assert test_stats["min_ms"] == 100.0
        assert test_stats["max_ms"] == 200.0
        assert test_stats["count"] == 3
        
        other_stats = stats["other_op"]
        assert other_stats["avg_ms"] == 50.0
        assert other_stats["count"] == 1
    
    def test_get_slow_operations(self):
        """Test getting slow operations."""
        profiler = PerformanceProfiler()
        
        profiler.record_metric("fast_op", 50.0)
        profiler.record_metric("slow_op", 1500.0)
        profiler.record_metric("medium_op", 800.0)
        
        slow_ops = profiler.get_slow_operations(threshold_ms=1000.0)
        
        assert len(slow_ops) == 1
        assert slow_ops[0].operation == "slow_op"
        assert slow_ops[0].duration_ms == 1500.0
    
    def test_clear(self):
        """Test clearing metrics."""
        profiler = PerformanceProfiler()
        
        profiler.record_metric("test_op", 100.0)
        assert len(profiler.metrics) == 1
        assert len(profiler.operation_stats) == 1
        
        profiler.clear()
        assert len(profiler.metrics) == 0
        assert len(profiler.operation_stats) == 0
    
    def test_max_metrics_limit(self):
        """Test that metrics are limited by max_metrics."""
        profiler = PerformanceProfiler(max_metrics=3)
        
        for i in range(5):
            profiler.record_metric(f"op_{i}", float(i * 100))
        
        # Should only keep last 3 metrics
        assert len(profiler.metrics) == 3
        assert profiler.metrics[0].operation == "op_2"
        assert profiler.metrics[2].operation == "op_4"


class TestProfiledOperation:
    """Test profiled operation context manager."""
    
    def test_profiled_operation(self):
        """Test sync profiled operation."""
        profiler = PerformanceProfiler()
        
        with ProfiledOperation(profiler, "test_sync"):
            time.sleep(0.01)  # 10ms
        
        assert len(profiler.metrics) == 1
        metric = profiler.metrics[0]
        assert metric.operation == "test_sync"
        assert metric.duration_ms >= 10.0  # Should be at least 10ms
    
    @pytest.mark.asyncio
    async def test_async_profiled_operation(self):
        """Test async profiled operation."""
        profiler = PerformanceProfiler()
        
        async with AsyncProfiledOperation(profiler, "test_async"):
            await asyncio.sleep(0.01)  # 10ms
        
        assert len(profiler.metrics) == 1
        metric = profiler.metrics[0]
        assert metric.operation == "test_async"
        assert metric.duration_ms >= 10.0  # Should be at least 10ms


class TestGlobalProfiler:
    """Test global profiler functions."""
    
    def test_get_profiler(self):
        """Test getting global profiler."""
        profiler1 = get_profiler()
        profiler2 = get_profiler()
        
        # Should be same instance
        assert profiler1 is profiler2
    
    def test_profile_operation_decorator(self):
        """Test sync operation decorator."""
        profiler = get_profiler()
        profiler.clear()
        
        @profile_operation("decorated_sync")
        def test_function():
            time.sleep(0.01)
            return "result"
        
        result = test_function()
        
        assert result == "result"
        assert len(profiler.metrics) == 1
        assert profiler.metrics[0].operation == "decorated_sync"
    
    @pytest.mark.asyncio
    async def test_profile_async_operation_decorator(self):
        """Test async operation decorator."""
        profiler = get_profiler()
        profiler.clear()
        
        @profile_async_operation("decorated_async")
        async def test_async_function():
            await asyncio.sleep(0.01)
            return "async_result"
        
        result = await test_async_function()
        
        assert result == "async_result"
        assert len(profiler.metrics) == 1
        assert profiler.metrics[0].operation == "decorated_async"


class TestProfilerIntegration:
    """Test profiler integration scenarios."""
    
    def test_operation_stats_memory_management(self):
        """Test that operation stats don't grow indefinitely."""
        profiler = PerformanceProfiler()
        
        # Record 150 metrics for same operation
        for i in range(150):
            profiler.record_metric("memory_test", float(i))
        
        # Should have trimmed when it exceeded 100 items
        # After 150 items: first trim at 101 (keeps 50), then grows to 99
        assert len(profiler.operation_stats["memory_test"]) == 99
        # Should contain values from first trim point onwards
        assert min(profiler.operation_stats["memory_test"]) == 51.0
        assert max(profiler.operation_stats["memory_test"]) == 149.0
    
    def test_multiple_operations_stats(self):
        """Test stats for multiple different operations."""
        profiler = PerformanceProfiler()
        
        operations = ["stt", "llm", "tts", "wake_word"]
        for op in operations:
            for i in range(5):
                profiler.record_metric(op, float(i * 10))
        
        stats = profiler.get_stats()
        
        assert len(stats) == 4
        for op in operations:
            assert op in stats
            assert stats[op]["count"] == 5
            assert stats[op]["avg_ms"] == 20.0  # (0+10+20+30+40)/5
