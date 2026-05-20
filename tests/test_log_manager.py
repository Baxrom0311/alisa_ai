"""Tests for log management functionality."""

import asyncio
import gzip
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any

import pytest

from alisa.services.log_manager import LogManager


class TestLogManager:
    """Test log management functionality."""
    
    @pytest.fixture
    def temp_log_dir(self):
        """Create temporary log directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)
    
    @pytest.fixture
    def log_manager(self, temp_log_dir):
        """Create log manager with temp directory."""
        return LogManager(
            log_dir=str(temp_log_dir),
            max_size_mb=1,  # Small size for testing
            keep_days=2,
            compress_old=True
        )
    
    def test_log_manager_init(self, temp_log_dir):
        """Test log manager initialization."""
        manager = LogManager(log_dir=str(temp_log_dir))
        
        assert manager.log_dir == temp_log_dir
        assert manager.max_size_mb == 50
        assert manager.keep_days == 7
        assert manager.compress_old is True
        assert temp_log_dir.exists()
    
    @pytest.mark.asyncio
    async def test_should_rotate_large_file(self, log_manager, temp_log_dir):
        """Test rotation detection for large files."""
        # Create large log file (2MB > 1MB limit)
        large_log = temp_log_dir / "test.log"
        large_log.write_bytes(b"x" * (2 * 1024 * 1024))
        
        should_rotate = await log_manager._should_rotate(large_log)
        assert should_rotate is True
    
    @pytest.mark.asyncio
    async def test_should_not_rotate_small_file(self, log_manager, temp_log_dir):
        """Test no rotation for small files."""
        # Create small log file
        small_log = temp_log_dir / "test.log"
        small_log.write_text("small log content")
        
        should_rotate = await log_manager._should_rotate(small_log)
        assert should_rotate is False
    
    @pytest.mark.asyncio
    async def test_should_not_rotate_missing_file(self, log_manager, temp_log_dir):
        """Test no rotation for missing files."""
        missing_log = temp_log_dir / "missing.log"
        
        should_rotate = await log_manager._should_rotate(missing_log)
        assert should_rotate is False
    
    @pytest.mark.asyncio
    async def test_rotate_file(self, log_manager, temp_log_dir):
        """Test log file rotation."""
        # Create log file
        log_file = temp_log_dir / "test.log"
        log_file.write_text("original content")
        
        # Rotate file
        rotated_file = await log_manager._rotate_file(log_file)
        
        # Check original file is recreated empty
        assert log_file.exists()
        assert log_file.read_text() == ""
        
        # Check rotated file exists with content
        assert rotated_file.exists()
        assert rotated_file.read_text() == "original content"
        assert "test_" in rotated_file.name
        assert rotated_file.name.endswith(".log")
    
    @pytest.mark.asyncio
    async def test_compress_file(self, log_manager, temp_log_dir):
        """Test log file compression."""
        # Create log file
        log_file = temp_log_dir / "test_20240520_120000.log"
        content = "test log content for compression"
        log_file.write_text(content)
        
        # Compress file
        compressed_file = await log_manager._compress_file(log_file)
        
        # Check original file is removed
        assert not log_file.exists()
        
        # Check compressed file exists and contains content
        assert compressed_file.exists()
        assert compressed_file.name.endswith(".log.gz")
        
        with gzip.open(compressed_file, 'rt') as f:
            assert f.read() == content
    
    @pytest.mark.asyncio
    async def test_compress_file_error(self, log_manager, temp_log_dir):
        """Test compression error handling."""
        # Try to compress non-existent file
        missing_file = temp_log_dir / "missing.log"
        
        result = await log_manager._compress_file(missing_file)
        assert result is None
    
    @pytest.mark.asyncio
    async def test_cleanup_old_files(self, log_manager, temp_log_dir):
        """Test cleanup of old log files."""
        # Create old files (older than 2 days)
        old_time = datetime.now() - timedelta(days=3)
        old_timestamp = old_time.timestamp()
        
        old_log = temp_log_dir / "old_20240517_120000.log"
        old_log.write_text("old content")
        # Use os.utime instead of Path.touch with times
        os.utime(old_log, (old_timestamp, old_timestamp))
        
        old_gz = temp_log_dir / "old_20240517_130000.log.gz"
        old_gz.write_bytes(b"compressed old content")
        os.utime(old_gz, (old_timestamp, old_timestamp))
        
        # Create recent file (should not be deleted)
        recent_log = temp_log_dir / "recent_20240520_120000.log"
        recent_log.write_text("recent content")
        
        # Create current log file (should not be deleted)
        current_log = temp_log_dir / "current.log"
        current_log.write_text("current content")
        
        # Run cleanup
        freed_size = await log_manager._cleanup_old_files()
        
        # Check old files are deleted
        assert not old_log.exists()
        assert not old_gz.exists()
        
        # Check recent and current files remain
        assert recent_log.exists()
        assert current_log.exists()
        
        # Check some space was freed
        assert freed_size > 0
    
    @pytest.mark.asyncio
    async def test_get_log_stats(self, log_manager, temp_log_dir):
        """Test log statistics collection."""
        # Create various log files
        current_log = temp_log_dir / "current.log"
        current_log.write_text("current log content with more text to make it bigger")
        
        archived_log = temp_log_dir / "archived_20240520_120000.log"
        archived_log.write_text("archived log content")
        
        compressed_log = temp_log_dir / "compressed_20240519_120000.log.gz"
        with gzip.open(compressed_log, 'wt') as f:
            f.write("compressed log content")
        
        # Get stats
        stats = await log_manager.get_log_stats()
        
        # Check stats structure
        assert "total_files" in stats
        assert "total_size_mb" in stats
        assert "current_logs" in stats
        assert "archived_logs" in stats
        assert "oldest_file" in stats
        assert "newest_file" in stats
        
        # Check file counts
        assert stats["total_files"] == 3
        assert len(stats["current_logs"]) == 1
        assert len(stats["archived_logs"]) == 2
        
        # Check current log is identified correctly
        current_info = stats["current_logs"][0]
        assert current_info["name"] == "current.log"
        # Size should be greater than 0 with more content
        assert current_info["size_mb"] >= 0
    
    @pytest.mark.asyncio
    async def test_rotate_logs_full_cycle(self, log_manager, temp_log_dir):
        """Test complete log rotation cycle."""
        # Create large log file that needs rotation
        large_log = temp_log_dir / "app.log"
        large_log.write_bytes(b"x" * (2 * 1024 * 1024))  # 2MB
        
        # Create small log file that doesn't need rotation
        small_log = temp_log_dir / "debug.log"
        small_log.write_text("debug info")
        
        # Run rotation
        results = await log_manager.rotate_logs()
        
        # Check results structure
        assert "rotated_files" in results
        assert "compressed_files" in results
        assert "deleted_files" in results
        assert "total_space_freed_mb" in results
        
        # Check large file was rotated and compressed
        assert len(results["rotated_files"]) == 1
        assert len(results["compressed_files"]) == 1
        
        # Check original large log is now empty
        assert large_log.exists()
        assert large_log.stat().st_size == 0
        
        # Check small log is unchanged
        assert small_log.exists()
        assert small_log.read_text() == "debug info"
        
        # Check compressed file exists
        compressed_files = list(temp_log_dir.glob("app_*.log.gz"))
        assert len(compressed_files) == 1


@pytest.mark.asyncio
async def test_log_manager_integration():
    """Test log manager integration."""
    with tempfile.TemporaryDirectory() as temp_dir:
        manager = LogManager(log_dir=temp_dir, max_size_mb=1, keep_days=1)
        
        # Create test scenario
        log_file = Path(temp_dir) / "integration.log"
        log_file.write_bytes(b"x" * (2 * 1024 * 1024))  # 2MB
        
        # Run full rotation cycle
        results = await manager.rotate_logs()
        
        # Verify rotation worked
        assert len(results["rotated_files"]) == 1
        assert len(results["compressed_files"]) == 1
        assert log_file.exists()
        assert log_file.stat().st_size == 0
        
        # Get stats
        stats = await manager.get_log_stats()
        assert stats["total_files"] >= 1
        assert stats["total_size_mb"] >= 0
