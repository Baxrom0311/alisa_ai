"""Task scheduler for periodic operations."""

import asyncio
import inspect
import structlog
from datetime import datetime, time
from typing import Callable, Dict, Any, Optional

logger = structlog.get_logger()


class TaskScheduler:
    """Simple task scheduler for periodic operations."""
    
    def __init__(self):
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.running = False
        self._task_handle: Optional[asyncio.Task] = None
    
    def add_daily_task(self, name: str, hour: int, minute: int, 
                      callback: Callable, *args, **kwargs):
        """Add a task that runs daily at specified time."""
        self.tasks[name] = {
            "type": "daily",
            "time": time(hour, minute),
            "callback": callback,
            "args": args,
            "kwargs": kwargs,
            "last_run": None
        }
        logger.info("daily_task_added", name=name, time=f"{hour:02d}:{minute:02d}")
    
    def add_interval_task(self, name: str, interval_minutes: int,
                         callback: Callable, *args, **kwargs):
        """Add a task that runs every N minutes."""
        self.tasks[name] = {
            "type": "interval",
            "interval_minutes": interval_minutes,
            "callback": callback,
            "args": args,
            "kwargs": kwargs,
            "last_run": None
        }
        logger.info("interval_task_added", name=name, interval=interval_minutes)
    
    def remove_task(self, name: str):
        """Remove a scheduled task."""
        if name in self.tasks:
            del self.tasks[name]
            logger.info("task_removed", name=name)
    
    async def start(self):
        """Start the scheduler."""
        if self.running:
            return
        
        self.running = True
        self._task_handle = asyncio.create_task(self._scheduler_loop())
        logger.info("scheduler_started")
    
    async def stop(self):
        """Stop the scheduler."""
        self.running = False
        if self._task_handle:
            self._task_handle.cancel()
            try:
                await self._task_handle
            except asyncio.CancelledError:
                pass
        logger.info("scheduler_stopped")
    
    async def _scheduler_loop(self):
        """Main scheduler loop."""
        while self.running:
            try:
                now = datetime.now()
                
                for name, task_info in self.tasks.items():
                    if await self._should_run_task(name, task_info, now):
                        await self._run_task(name, task_info, now)
                
                # Check every minute
                await asyncio.sleep(60)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("scheduler_loop_error", error=str(e))
                await asyncio.sleep(60)
    
    async def _should_run_task(self, name: str, task_info: Dict[str, Any], 
                              now: datetime) -> bool:
        """Check if a task should run now."""
        last_run = task_info.get("last_run")
        
        if task_info["type"] == "daily":
            target_time = task_info["time"]
            today_target = now.replace(
                hour=target_time.hour,
                minute=target_time.minute,
                second=0,
                microsecond=0
            )
            
            # Run if current time is past target time and we haven't run today
            if now >= today_target:
                if last_run is None or last_run.date() < now.date():
                    return True
        
        elif task_info["type"] == "interval":
            interval_minutes = task_info["interval_minutes"]
            
            if last_run is None:
                return True
            
            minutes_since_last = (now - last_run).total_seconds() / 60
            if minutes_since_last >= interval_minutes:
                return True
        
        return False
    
    async def _run_task(self, name: str, task_info: Dict[str, Any], now: datetime):
        """Execute a scheduled task."""
        try:
            logger.info("running_scheduled_task", name=name)
            
            callback = task_info["callback"]
            args = task_info.get("args", ())
            kwargs = task_info.get("kwargs", {})
            
            # Run callback (handle both sync and async)
            if inspect.iscoroutinefunction(callback):
                await callback(*args, **kwargs)
            else:
                callback(*args, **kwargs)
            
            # Update last run time
            task_info["last_run"] = now
            
            logger.info("scheduled_task_completed", name=name)
            
        except Exception as e:
            logger.error("scheduled_task_error", name=name, error=str(e))


# Global scheduler instance
_scheduler: Optional[TaskScheduler] = None


def get_scheduler() -> TaskScheduler:
    """Get the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = TaskScheduler()
    return _scheduler


# Convenience functions for common scheduling patterns
def schedule_daily_news(hour: int = 8, minute: int = 0):
    """Schedule daily news reading."""
    from alisa.brain.online import get_news
    
    def news_task():
        news = get_news()
        if news:
            logger.info("daily_news", content=news)
    
    scheduler = get_scheduler()
    scheduler.add_daily_task("daily_news", hour, minute, news_task)


def schedule_health_check(interval_minutes: int = 30):
    """Schedule periodic health checks."""
    from alisa.services.health import is_system_healthy, get_system_stats
    
    def health_task():
        if not is_system_healthy():
            stats = get_system_stats()
            logger.warning("system_health_warning", **stats)
    
    scheduler = get_scheduler()
    scheduler.add_interval_task("health_check", interval_minutes, health_task)
