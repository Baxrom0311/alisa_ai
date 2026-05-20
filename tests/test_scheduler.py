"""Tests for scheduler module."""

import asyncio
import pytest
from datetime import datetime, time
from unittest.mock import Mock, patch

from alisa.services.scheduler import TaskScheduler, get_scheduler, schedule_daily_news, schedule_health_check


class TestTaskScheduler:
    """Test TaskScheduler functionality."""
    
    def test_add_daily_task(self):
        """Test adding a daily task."""
        scheduler = TaskScheduler()
        callback = Mock()
        
        scheduler.add_daily_task("test_daily", 9, 30, callback, "arg1", key="value")
        
        assert "test_daily" in scheduler.tasks
        task = scheduler.tasks["test_daily"]
        assert task["type"] == "daily"
        assert task["time"] == time(9, 30)
        assert task["callback"] == callback
        assert task["args"] == ("arg1",)
        assert task["kwargs"] == {"key": "value"}
        assert task["last_run"] is None
    
    def test_add_interval_task(self):
        """Test adding an interval task."""
        scheduler = TaskScheduler()
        callback = Mock()
        
        scheduler.add_interval_task("test_interval", 15, callback, "arg1", key="value")
        
        assert "test_interval" in scheduler.tasks
        task = scheduler.tasks["test_interval"]
        assert task["type"] == "interval"
        assert task["interval_minutes"] == 15
        assert task["callback"] == callback
        assert task["args"] == ("arg1",)
        assert task["kwargs"] == {"key": "value"}
        assert task["last_run"] is None
    
    def test_remove_task(self):
        """Test removing a task."""
        scheduler = TaskScheduler()
        callback = Mock()
        
        scheduler.add_daily_task("test_task", 10, 0, callback)
        assert "test_task" in scheduler.tasks
        
        scheduler.remove_task("test_task")
        assert "test_task" not in scheduler.tasks
    
    def test_remove_nonexistent_task(self):
        """Test removing a task that doesn't exist."""
        scheduler = TaskScheduler()
        # Should not raise an error
        scheduler.remove_task("nonexistent")
    
    @pytest.mark.asyncio
    async def test_start_stop(self):
        """Test starting and stopping the scheduler."""
        scheduler = TaskScheduler()
        
        assert not scheduler.running
        assert scheduler._task_handle is None
        
        await scheduler.start()
        assert scheduler.running
        assert scheduler._task_handle is not None
        
        await scheduler.stop()
        assert not scheduler.running
    
    @pytest.mark.asyncio
    async def test_start_already_running(self):
        """Test starting scheduler when already running."""
        scheduler = TaskScheduler()
        
        await scheduler.start()
        first_handle = scheduler._task_handle
        
        # Starting again should not create a new task
        await scheduler.start()
        assert scheduler._task_handle == first_handle
        
        await scheduler.stop()
    
    @pytest.mark.parametrize("current_time,target_hour,target_minute,last_run_date,should_run", [
        # Should run: current time is past target and no run today
        (datetime(2023, 5, 15, 10, 0), 9, 30, None, True),
        (datetime(2023, 5, 15, 10, 0), 9, 30, datetime(2023, 5, 14, 9, 30), True),
        
        # Should not run: current time is before target
        (datetime(2023, 5, 15, 9, 0), 9, 30, None, False),
        
        # Should not run: already ran today
        (datetime(2023, 5, 15, 10, 0), 9, 30, datetime(2023, 5, 15, 9, 30), False),
    ])
    @pytest.mark.asyncio
    async def test_should_run_daily_task(self, current_time, target_hour, target_minute, last_run_date, should_run):
        """Test daily task scheduling logic."""
        scheduler = TaskScheduler()
        
        task_info = {
            "type": "daily",
            "time": time(target_hour, target_minute),
            "last_run": last_run_date
        }
        
        result = await scheduler._should_run_task("test", task_info, current_time)
        assert result == should_run
    
    @pytest.mark.parametrize("current_time,interval_minutes,last_run_time,should_run", [
        # Should run: no previous run
        (datetime(2023, 5, 15, 10, 0), 30, None, True),
        
        # Should run: interval has passed
        (datetime(2023, 5, 15, 10, 30), 30, datetime(2023, 5, 15, 10, 0), True),
        (datetime(2023, 5, 15, 11, 0), 30, datetime(2023, 5, 15, 10, 0), True),
        
        # Should not run: interval has not passed
        (datetime(2023, 5, 15, 10, 15), 30, datetime(2023, 5, 15, 10, 0), False),
        (datetime(2023, 5, 15, 10, 29), 30, datetime(2023, 5, 15, 10, 0), False),
    ])
    @pytest.mark.asyncio
    async def test_should_run_interval_task(self, current_time, interval_minutes, last_run_time, should_run):
        """Test interval task scheduling logic."""
        scheduler = TaskScheduler()
        
        task_info = {
            "type": "interval",
            "interval_minutes": interval_minutes,
            "last_run": last_run_time
        }
        
        result = await scheduler._should_run_task("test", task_info, current_time)
        assert result == should_run
    
    @pytest.mark.asyncio
    async def test_run_sync_task(self):
        """Test running a synchronous task."""
        scheduler = TaskScheduler()
        callback = Mock()
        
        task_info = {
            "callback": callback,
            "args": ("arg1", "arg2"),
            "kwargs": {"key": "value"}
        }
        
        now = datetime.now()
        await scheduler._run_task("test", task_info, now)
        
        callback.assert_called_once_with("arg1", "arg2", key="value")
        assert task_info["last_run"] == now
    
    @pytest.mark.asyncio
    async def test_run_async_task(self):
        """Test running an asynchronous task."""
        scheduler = TaskScheduler()
        callback = Mock()
        
        async def async_callback(*args, **kwargs):
            callback(*args, **kwargs)
        
        task_info = {
            "callback": async_callback,
            "args": ("arg1", "arg2"),
            "kwargs": {"key": "value"}
        }
        
        now = datetime.now()
        await scheduler._run_task("test", task_info, now)
        
        callback.assert_called_once_with("arg1", "arg2", key="value")
        assert task_info["last_run"] == now
    
    @pytest.mark.asyncio
    async def test_run_task_exception_handling(self):
        """Test that task exceptions are handled gracefully."""
        scheduler = TaskScheduler()
        
        def failing_callback():
            raise ValueError("Test error")
        
        task_info = {
            "callback": failing_callback,
            "args": (),
            "kwargs": {}
        }
        
        now = datetime.now()
        # Should not raise an exception
        await scheduler._run_task("test", task_info, now)
        
        # last_run should not be updated on failure
        assert task_info.get("last_run") is None


class TestSchedulerGlobal:
    """Test global scheduler functions."""
    
    def test_get_scheduler_singleton(self):
        """Test that get_scheduler returns the same instance."""
        scheduler1 = get_scheduler()
        scheduler2 = get_scheduler()
        
        assert scheduler1 is scheduler2
        assert isinstance(scheduler1, TaskScheduler)
    
    @patch('alisa.brain.online.get_news')
    def test_schedule_daily_news(self, mock_get_news):
        """Test scheduling daily news."""
        mock_get_news.return_value = "Test news"
        
        # Clear any existing tasks
        scheduler = get_scheduler()
        scheduler.tasks.clear()
        
        schedule_daily_news(9, 0)
        
        assert "daily_news" in scheduler.tasks
        task = scheduler.tasks["daily_news"]
        assert task["type"] == "daily"
        assert task["time"] == time(9, 0)
        
        # Test the callback
        task["callback"]()
        mock_get_news.assert_called_once()
    
    @patch('alisa.services.health.is_system_healthy')
    @patch('alisa.services.health.get_system_stats')
    def test_schedule_health_check(self, mock_get_stats, mock_is_healthy):
        """Test scheduling health checks."""
        mock_is_healthy.return_value = False
        mock_get_stats.return_value = {"cpu": 80, "memory": 90}
        
        # Clear any existing tasks
        scheduler = get_scheduler()
        scheduler.tasks.clear()
        
        schedule_health_check(15)
        
        assert "health_check" in scheduler.tasks
        task = scheduler.tasks["health_check"]
        assert task["type"] == "interval"
        assert task["interval_minutes"] == 15
        
        # Test the callback
        task["callback"]()
        mock_is_healthy.assert_called_once()
        mock_get_stats.assert_called_once()
    
    @patch('alisa.services.health.is_system_healthy')
    def test_schedule_health_check_healthy(self, mock_is_healthy):
        """Test health check when system is healthy."""
        mock_is_healthy.return_value = True
        
        # Clear any existing tasks
        scheduler = get_scheduler()
        scheduler.tasks.clear()
        
        schedule_health_check(15)
        
        # Test the callback - should not call get_system_stats when healthy
        with patch('alisa.services.health.get_system_stats') as mock_get_stats:
            scheduler.tasks["health_check"]["callback"]()
            mock_is_healthy.assert_called_once()
            mock_get_stats.assert_not_called()


class TestSchedulerIntegration:
    """Integration tests for scheduler."""
    
    @pytest.mark.asyncio
    async def test_scheduler_loop_execution(self):
        """Test that scheduler loop executes tasks."""
        scheduler = TaskScheduler()
        callback = Mock()
        
        # Add a task that should run immediately
        scheduler.add_interval_task("test_task", 1, callback)  # 1 minute interval
        
        # Mock _should_run_task to return True once, then False
        call_count = 0
        original_should_run = scheduler._should_run_task
        
        async def mock_should_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return True
            return False
        
        scheduler._should_run_task = mock_should_run
        
        # Start scheduler and let it run briefly
        await scheduler.start()
        await asyncio.sleep(0.1)  # Let it run one iteration
        await scheduler.stop()
        
        # Verify task was executed
        callback.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_scheduler_exception_isolation(self):
        """Test that one failing task doesn't stop others."""
        scheduler = TaskScheduler()
        
        def failing_task():
            raise ValueError("Task failed")
        
        good_callback = Mock()
        
        scheduler.add_interval_task("failing_task", 1, failing_task)
        scheduler.add_interval_task("good_task", 1, good_callback)
        
        # Mock _should_run_task to return True for both tasks
        async def mock_should_run(name, *args, **kwargs):
            return True
        
        scheduler._should_run_task = mock_should_run
        
        # Start scheduler and let it run briefly
        await scheduler.start()
        await asyncio.sleep(0.1)
        await scheduler.stop()
        
        # Good task should still execute despite failing task
        good_callback.assert_called_once()
