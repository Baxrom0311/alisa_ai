"""Memory management utilities for Raspberry Pi optimization."""

import gc
import psutil
import structlog
from typing import Dict, Any

logger = structlog.get_logger()


class MemoryManager:
    """Manages memory usage and cleanup for Pi optimization."""
    
    def __init__(self, max_memory_mb: int = 3000):
        self.max_memory_mb = max_memory_mb
        self.cleanup_threshold = 0.8  # Cleanup at 80% of max
        
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get current memory statistics."""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            
            return {
                "rss_mb": memory_info.rss / 1024 / 1024,
                "vms_mb": memory_info.vms / 1024 / 1024,
                "percent": process.memory_percent(),
                "available_mb": psutil.virtual_memory().available / 1024 / 1024,
                "gc_objects": len(gc.get_objects())
            }
        except Exception as e:
            logger.error("memory_stats_error", error=str(e))
            return {}
    
    def should_cleanup(self) -> bool:
        """Check if memory cleanup is needed."""
        stats = self.get_memory_stats()
        if not stats:
            return False
            
        current_mb = stats.get("rss_mb", 0)
        return current_mb > (self.max_memory_mb * self.cleanup_threshold)
    
    def cleanup(self) -> Dict[str, Any]:
        """Perform memory cleanup."""
        before_stats = self.get_memory_stats()
        
        # Force garbage collection
        collected = gc.collect()
        
        after_stats = self.get_memory_stats()
        
        cleanup_result = {
            "objects_collected": collected,
            "memory_before_mb": before_stats.get("rss_mb", 0),
            "memory_after_mb": after_stats.get("rss_mb", 0),
            "memory_freed_mb": before_stats.get("rss_mb", 0) - after_stats.get("rss_mb", 0)
        }
        
        logger.info("memory_cleanup_completed", **cleanup_result)
        return cleanup_result
    
    def monitor_and_cleanup(self) -> bool:
        """Monitor memory and cleanup if needed. Returns True if cleanup was performed."""
        if self.should_cleanup():
            self.cleanup()
            return True
        return False


# Global memory manager instance
_memory_manager = None


def get_memory_manager() -> MemoryManager:
    """Get global memory manager instance."""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager
