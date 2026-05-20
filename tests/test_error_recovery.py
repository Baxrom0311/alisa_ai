"""Tests for error recovery system."""

import asyncio
import pytest
import time
from unittest.mock import AsyncMock, MagicMock

from alisa.services.error_recovery import (
    ErrorRecoveryManager, ErrorSeverity, ErrorEvent,
    get_recovery_manager, with_error_recovery, ErrorRecoveryContext,
    restart_component_strategy, clear_cache_strategy
)


class TestErrorRecoveryManager:
    """Test error recovery manager."""
    
    def test_init(self):
        """Test manager initialization."""
        manager = ErrorRecoveryManager()
        assert manager.error_history == []
        assert manager.recovery_strategies == {}
        assert manager.component_health == {}
    
    def test_register_recovery_strategy(self):
        """Test registering recovery strategies."""
        manager = ErrorRecoveryManager()
        
        def dummy_strategy(error_event):
            return True
        
        manager.register_recovery_strategy("test_component", dummy_strategy)
        assert "test_component" in manager.recovery_strategies
        assert manager.recovery_strategies["test_component"] == dummy_strategy
    
    def test_record_error(self):
        """Test error recording."""
        manager = ErrorRecoveryManager()
        error = ValueError("Test error")
        
        manager.record_error("test_component", error, ErrorSeverity.HIGH)
        
        assert len(manager.error_history) == 1
        event = manager.error_history[0]
        assert event.component == "test_component"
        assert event.error_type == "ValueError"
        assert event.message == "Test error"
        assert event.severity == ErrorSeverity.HIGH
        assert manager.component_health["test_component"] is False
    
    def test_get_component_health(self):
        """Test component health checking."""
        manager = ErrorRecoveryManager()
        
        # Default health should be True
        assert manager.get_component_health("unknown_component") is True
        
        # After error, health should be False
        manager.record_error("test_component", ValueError("test"))
        assert manager.get_component_health("test_component") is False
    
    def test_get_error_count(self):
        """Test error counting."""
        manager = ErrorRecoveryManager()
        
        # Add some errors
        manager.record_error("comp1", ValueError("error1"))
        manager.record_error("comp2", ValueError("error2"))
        manager.record_error("comp1", ValueError("error3"))
        
        assert manager.get_error_count() == 3
        assert manager.get_error_count("comp1") == 2
        assert manager.get_error_count("comp2") == 1
        assert manager.get_error_count("comp3") == 0
    
    def test_get_recent_errors(self):
        """Test getting recent errors."""
        manager = ErrorRecoveryManager()
        
        # Add errors with slight delay to ensure different timestamps
        manager.record_error("comp1", ValueError("error1"))
        time.sleep(0.01)
        manager.record_error("comp2", ValueError("error2"))
        
        recent = manager.get_recent_errors(limit=1)
        assert len(recent) == 1
        assert recent[0].component == "comp2"  # Most recent
    
    def test_is_component_failing(self):
        """Test component failure detection."""
        manager = ErrorRecoveryManager()
        
        # Add multiple errors quickly
        for i in range(6):
            manager.record_error("failing_comp", ValueError(f"error{i}"))
        
        assert manager.is_component_failing("failing_comp", error_threshold=5, time_window=10)
        assert not manager.is_component_failing("healthy_comp", error_threshold=5, time_window=10)
    
    def test_get_system_health_summary(self):
        """Test system health summary."""
        manager = ErrorRecoveryManager()
        
        # Add some errors
        manager.record_error("comp1", ValueError("error1"), ErrorSeverity.LOW)
        manager.record_error("comp2", ValueError("error2"), ErrorSeverity.HIGH)
        
        summary = manager.get_system_health_summary()
        
        assert summary["total_errors"] == 2
        assert summary["total_components"] == 2
        assert summary["healthy_components"] == 0  # Both components have errors
        assert summary["health_percentage"] == 0.0
        assert "comp1" in summary["failing_components"]
        assert "comp2" in summary["failing_components"]
        assert summary["severity_breakdown"]["low"] == 1
        assert summary["severity_breakdown"]["high"] == 1
    
    @pytest.mark.asyncio
    async def test_recovery_attempt(self):
        """Test recovery attempt."""
        manager = ErrorRecoveryManager()
        
        # Mock recovery strategy
        recovery_mock = AsyncMock(return_value=True)
        manager.register_recovery_strategy("test_comp", recovery_mock)
        
        # Record error (this should trigger recovery)
        manager.record_error("test_comp", ValueError("test error"))
        
        # Wait for recovery task to complete
        await asyncio.sleep(0.1)
        
        # Check that recovery was attempted
        recovery_mock.assert_called_once()
        assert manager.component_health["test_comp"] is True  # Should be healthy after successful recovery


class TestRecoveryStrategies:
    """Test recovery strategies."""
    
    @pytest.mark.asyncio
    async def test_restart_component_strategy(self):
        """Test component restart strategy."""
        error_event = ErrorEvent(
            timestamp=time.time(),
            component="test_comp",
            error_type="ValueError",
            message="test error",
            severity=ErrorSeverity.MEDIUM
        )
        
        result = await restart_component_strategy(error_event)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_clear_cache_strategy(self):
        """Test cache clear strategy."""
        error_event = ErrorEvent(
            timestamp=time.time(),
            component="test_comp",
            error_type="ValueError",
            message="test error",
            severity=ErrorSeverity.MEDIUM
        )
        
        result = await clear_cache_strategy(error_event)
        assert result is True


class TestErrorRecoveryDecorator:
    """Test error recovery decorator."""
    
    def test_sync_function_success(self):
        """Test decorator with successful sync function."""
        @with_error_recovery("test_comp")
        def test_func():
            return "success"
        
        result = test_func()
        assert result == "success"
        
        # No errors should be recorded
        manager = get_recovery_manager()
        assert manager.get_error_count("test_comp") == 0
    
    def test_sync_function_error(self):
        """Test decorator with failing sync function."""
        @with_error_recovery("test_comp")
        def test_func():
            raise ValueError("test error")
        
        manager = get_recovery_manager()
        initial_count = manager.get_error_count("test_comp")
        
        with pytest.raises(ValueError):
            test_func()
        
        # Error should be recorded
        assert manager.get_error_count("test_comp") == initial_count + 1
    
    @pytest.mark.asyncio
    async def test_async_function_success(self):
        """Test decorator with successful async function."""
        @with_error_recovery("test_comp_async_success")
        async def test_func():
            return "success"
        
        result = await test_func()
        assert result == "success"
        
        # No errors should be recorded for this specific component
        manager = get_recovery_manager()
        assert manager.get_error_count("test_comp_async_success") == 0
    
    @pytest.mark.asyncio
    async def test_async_function_error(self):
        """Test decorator with failing async function."""
        @with_error_recovery("test_comp")
        async def test_func():
            raise ValueError("test error")
        
        manager = get_recovery_manager()
        initial_count = manager.get_error_count("test_comp")
        
        with pytest.raises(ValueError):
            await test_func()
        
        # Error should be recorded
        assert manager.get_error_count("test_comp") == initial_count + 1


class TestErrorRecoveryContext:
    """Test error recovery context manager."""
    
    def test_context_success(self):
        """Test context manager with successful operation."""
        manager = get_recovery_manager()
        initial_count = manager.get_error_count("test_comp")
        
        with ErrorRecoveryContext("test_comp"):
            pass  # No error
        
        # No errors should be recorded
        assert manager.get_error_count("test_comp") == initial_count
    
    def test_context_error(self):
        """Test context manager with error."""
        manager = get_recovery_manager()
        initial_count = manager.get_error_count("test_comp")
        
        with pytest.raises(ValueError):
            with ErrorRecoveryContext("test_comp"):
                raise ValueError("test error")
        
        # Error should be recorded
        assert manager.get_error_count("test_comp") == initial_count + 1
    
    @pytest.mark.asyncio
    async def test_async_context_success(self):
        """Test async context manager with successful operation."""
        manager = get_recovery_manager()
        initial_count = manager.get_error_count("test_comp")
        
        async with ErrorRecoveryContext("test_comp"):
            pass  # No error
        
        # No errors should be recorded
        assert manager.get_error_count("test_comp") == initial_count
    
    @pytest.mark.asyncio
    async def test_async_context_error(self):
        """Test async context manager with error."""
        manager = get_recovery_manager()
        initial_count = manager.get_error_count("test_comp")
        
        with pytest.raises(ValueError):
            async with ErrorRecoveryContext("test_comp"):
                raise ValueError("test error")
        
        # Error should be recorded
        assert manager.get_error_count("test_comp") == initial_count + 1


class TestGlobalManager:
    """Test global manager instance."""
    
    def test_get_recovery_manager_singleton(self):
        """Test that get_recovery_manager returns singleton."""
        manager1 = get_recovery_manager()
        manager2 = get_recovery_manager()
        
        assert manager1 is manager2


if __name__ == "__main__":
    pytest.main([__file__])
