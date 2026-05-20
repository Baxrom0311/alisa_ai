"""Error recovery and resilience system for Alisa AI Assistant."""

import asyncio
import logging
import time
import inspect
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass
from enum import Enum

import structlog

logger = structlog.get_logger()


class ErrorSeverity(Enum):
    """Error severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ErrorEvent:
    """Error event record."""
    timestamp: float
    component: str
    error_type: str
    message: str
    severity: ErrorSeverity
    recovery_attempted: bool = False
    recovery_successful: bool = False


class ErrorRecoveryManager:
    """Manages error recovery and system resilience."""
    
    def __init__(self):
        self.error_history: List[ErrorEvent] = []
        self.recovery_strategies: Dict[str, Callable] = {}
        self.component_health: Dict[str, bool] = {}
        self.max_history = 1000
        self.recovery_cooldown = 60.0  # seconds
        self.last_recovery_attempt: Dict[str, float] = {}
        
    def register_recovery_strategy(self, component: str, strategy: Callable):
        """Register a recovery strategy for a component."""
        self.recovery_strategies[component] = strategy
        logger.info("recovery_strategy_registered", component=component)
    
    def record_error(self, component: str, error: Exception, severity: ErrorSeverity = ErrorSeverity.MEDIUM):
        """Record an error event."""
        error_event = ErrorEvent(
            timestamp=time.time(),
            component=component,
            error_type=type(error).__name__,
            message=str(error),
            severity=severity
        )
        
        self.error_history.append(error_event)
        self.component_health[component] = False
        
        # Trim history if too long
        if len(self.error_history) > self.max_history:
            self.error_history = self.error_history[-self.max_history:]
        
        logger.error("error_recorded", 
                    component=component, 
                    error_type=error_event.error_type,
                    severity=severity.value,
                    message=str(error))
        
        # Attempt recovery if strategy exists and cooldown passed
        if component in self.recovery_strategies:
            last_attempt = self.last_recovery_attempt.get(component, 0)
            if time.time() - last_attempt > self.recovery_cooldown:
                asyncio.create_task(self._attempt_recovery(error_event))
    
    async def _attempt_recovery(self, error_event: ErrorEvent):
        """Attempt to recover from an error."""
        component = error_event.component
        strategy = self.recovery_strategies.get(component)
        
        if not strategy:
            return
        
        try:
            logger.info("recovery_attempt_started", component=component)
            error_event.recovery_attempted = True
            self.last_recovery_attempt[component] = time.time()
            
            # Call recovery strategy
            if inspect.iscoroutinefunction(strategy):
                success = await strategy(error_event)
            else:
                success = strategy(error_event)
            
            error_event.recovery_successful = success
            
            if success:
                self.component_health[component] = True
                logger.info("recovery_successful", component=component)
            else:
                logger.warning("recovery_failed", component=component)
                
        except Exception as e:
            logger.error("recovery_strategy_error", 
                        component=component, 
                        error=str(e))
            error_event.recovery_successful = False
    
    def get_component_health(self, component: str) -> bool:
        """Get health status of a component."""
        return self.component_health.get(component, True)
    
    def get_error_count(self, component: str = None, since_minutes: int = 60) -> int:
        """Get error count for a component in the last N minutes."""
        cutoff = time.time() - (since_minutes * 60)
        
        if component:
            return len([e for e in self.error_history 
                       if e.component == component and e.timestamp > cutoff])
        else:
            return len([e for e in self.error_history if e.timestamp > cutoff])
    
    def get_recent_errors(self, limit: int = 10) -> List[ErrorEvent]:
        """Get recent error events."""
        return sorted(self.error_history, key=lambda x: x.timestamp, reverse=True)[:limit]
    
    def is_component_failing(self, component: str, error_threshold: int = 5, time_window: int = 10) -> bool:
        """Check if a component is failing (too many errors in time window)."""
        recent_errors = self.get_error_count(component, time_window)
        return recent_errors >= error_threshold
    
    def get_system_health_summary(self) -> Dict[str, Any]:
        """Get overall system health summary."""
        total_errors = len(self.error_history)
        recent_errors = self.get_error_count(since_minutes=60)
        
        # Component health summary
        healthy_components = sum(1 for health in self.component_health.values() if health)
        total_components = len(self.component_health)
        
        # Error severity breakdown
        severity_counts = {}
        for severity in ErrorSeverity:
            severity_counts[severity.value] = len([e for e in self.error_history 
                                                  if e.severity == severity])
        
        return {
            "total_errors": total_errors,
            "recent_errors_1h": recent_errors,
            "healthy_components": healthy_components,
            "total_components": total_components,
            "health_percentage": (healthy_components / max(total_components, 1)) * 100,
            "severity_breakdown": severity_counts,
            "failing_components": [comp for comp, health in self.component_health.items() 
                                 if not health]
        }


# Global instance
_recovery_manager: Optional[ErrorRecoveryManager] = None


def get_recovery_manager() -> ErrorRecoveryManager:
    """Get global error recovery manager."""
    global _recovery_manager
    if _recovery_manager is None:
        _recovery_manager = ErrorRecoveryManager()
    return _recovery_manager


# Common recovery strategies

async def restart_component_strategy(error_event: ErrorEvent) -> bool:
    """Generic component restart strategy."""
    component = error_event.component
    logger.info("attempting_component_restart", component=component)
    
    try:
        # This is a placeholder - actual restart logic would be component-specific
        await asyncio.sleep(1)  # Simulate restart delay
        logger.info("component_restart_completed", component=component)
        return True
    except Exception as e:
        logger.error("component_restart_failed", component=component, error=str(e))
        return False


async def clear_cache_strategy(error_event: ErrorEvent) -> bool:
    """Clear component cache strategy."""
    component = error_event.component
    logger.info("attempting_cache_clear", component=component)
    
    try:
        # This is a placeholder - actual cache clearing would be component-specific
        await asyncio.sleep(0.5)
        logger.info("cache_clear_completed", component=component)
        return True
    except Exception as e:
        logger.error("cache_clear_failed", component=component, error=str(e))
        return False


def setup_default_recovery_strategies():
    """Setup default recovery strategies for common components."""
    manager = get_recovery_manager()
    
    # Register default strategies
    manager.register_recovery_strategy("llm_manager", restart_component_strategy)
    manager.register_recovery_strategy("voice_pipeline", restart_component_strategy)
    manager.register_recovery_strategy("telegram_bot", restart_component_strategy)
    manager.register_recovery_strategy("web_dashboard", restart_component_strategy)
    manager.register_recovery_strategy("memory_manager", clear_cache_strategy)
    
    logger.info("default_recovery_strategies_setup")


# Decorator for automatic error recording

def with_error_recovery(component: str, severity: ErrorSeverity = ErrorSeverity.MEDIUM):
    """Decorator to automatically record errors and attempt recovery."""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                get_recovery_manager().record_error(component, e, severity)
                raise
        
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                get_recovery_manager().record_error(component, e, severity)
                raise
        
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# Context manager for error recovery

class ErrorRecoveryContext:
    """Context manager for error recovery."""
    
    def __init__(self, component: str, severity: ErrorSeverity = ErrorSeverity.MEDIUM):
        self.component = component
        self.severity = severity
        self.manager = get_recovery_manager()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.manager.record_error(self.component, exc_val, self.severity)
        return False  # Don't suppress the exception
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.manager.record_error(self.component, exc_val, self.severity)
        return False  # Don't suppress the exception


# Initialize default strategies on import
setup_default_recovery_strategies()
