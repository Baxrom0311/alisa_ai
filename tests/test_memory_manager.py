"""Tests for memory manager."""

import pytest
from unittest.mock import Mock, patch
from alisa.core.memory_manager import MemoryManager, get_memory_manager


class TestMemoryManager:
    """Test memory management functionality."""
    
    def test_init(self):
        """Test memory manager initialization."""
        manager = MemoryManager(max_memory_mb=2000)
        assert manager.max_memory_mb == 2000
        assert manager.cleanup_threshold == 0.8
    
    @patch('alisa.core.memory_manager.psutil.Process')
    @patch('alisa.core.memory_manager.psutil.virtual_memory')
    def test_get_memory_stats_success(self, mock_virtual_memory, mock_process):
        """Test successful memory stats retrieval."""
        # Mock process memory info
        mock_memory_info = Mock()
        mock_memory_info.rss = 1024 * 1024 * 500  # 500 MB
        mock_memory_info.vms = 1024 * 1024 * 800  # 800 MB
        
        mock_proc = Mock()
        mock_proc.memory_info.return_value = mock_memory_info
        mock_proc.memory_percent.return_value = 25.0
        mock_process.return_value = mock_proc
        
        # Mock virtual memory
        mock_vm = Mock()
        mock_vm.available = 1024 * 1024 * 1024 * 2  # 2 GB
        mock_virtual_memory.return_value = mock_vm
        
        manager = MemoryManager()
        
        with patch('alisa.core.memory_manager.gc.get_objects', return_value=['obj1', 'obj2']):
            stats = manager.get_memory_stats()
        
        assert stats['rss_mb'] == 500.0
        assert stats['vms_mb'] == 800.0
        assert stats['percent'] == 25.0
        assert stats['available_mb'] == 2048.0
        assert stats['gc_objects'] == 2
    
    @patch('alisa.core.memory_manager.psutil.Process')
    def test_get_memory_stats_error(self, mock_process):
        """Test memory stats error handling."""
        mock_process.side_effect = Exception("Process error")
        
        manager = MemoryManager()
        stats = manager.get_memory_stats()
        
        assert stats == {}
    
    def test_should_cleanup_true(self):
        """Test cleanup threshold detection - should cleanup."""
        manager = MemoryManager(max_memory_mb=1000)
        
        with patch.object(manager, 'get_memory_stats', return_value={'rss_mb': 850}):
            assert manager.should_cleanup() is True
    
    def test_should_cleanup_false(self):
        """Test cleanup threshold detection - should not cleanup."""
        manager = MemoryManager(max_memory_mb=1000)
        
        with patch.object(manager, 'get_memory_stats', return_value={'rss_mb': 500}):
            assert manager.should_cleanup() is False
    
    def test_should_cleanup_no_stats(self):
        """Test cleanup when stats unavailable."""
        manager = MemoryManager()
        
        with patch.object(manager, 'get_memory_stats', return_value={}):
            assert manager.should_cleanup() is False
    
    @patch('alisa.core.memory_manager.gc.collect')
    def test_cleanup(self, mock_gc_collect):
        """Test memory cleanup process."""
        mock_gc_collect.return_value = 42  # Objects collected
        
        manager = MemoryManager()
        
        # Mock before and after stats
        stats_before = {'rss_mb': 800}
        stats_after = {'rss_mb': 750}
        
        with patch.object(manager, 'get_memory_stats', side_effect=[stats_before, stats_after]):
            result = manager.cleanup()
        
        assert result['objects_collected'] == 42
        assert result['memory_before_mb'] == 800
        assert result['memory_after_mb'] == 750
        assert result['memory_freed_mb'] == 50
        
        mock_gc_collect.assert_called_once()
    
    def test_monitor_and_cleanup_needed(self):
        """Test monitor and cleanup when cleanup is needed."""
        manager = MemoryManager()
        
        with patch.object(manager, 'should_cleanup', return_value=True), \
             patch.object(manager, 'cleanup', return_value={'freed': 100}) as mock_cleanup:
            
            result = manager.monitor_and_cleanup()
            
            assert result is True
            mock_cleanup.assert_called_once()
    
    def test_monitor_and_cleanup_not_needed(self):
        """Test monitor and cleanup when cleanup is not needed."""
        manager = MemoryManager()
        
        with patch.object(manager, 'should_cleanup', return_value=False), \
             patch.object(manager, 'cleanup') as mock_cleanup:
            
            result = manager.monitor_and_cleanup()
            
            assert result is False
            mock_cleanup.assert_not_called()


class TestMemoryManagerGlobal:
    """Test global memory manager functions."""
    
    def test_get_memory_manager_singleton(self):
        """Test that get_memory_manager returns singleton."""
        manager1 = get_memory_manager()
        manager2 = get_memory_manager()
        
        assert manager1 is manager2
        assert isinstance(manager1, MemoryManager)
