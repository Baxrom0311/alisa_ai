"""Log management and rotation for Alisa AI Assistant."""

import asyncio
import gzip
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import structlog

logger = structlog.get_logger()


class LogManager:
    """Manages log files and rotation for Pi deployment."""
    
    def __init__(self, log_dir: str = None, max_size_mb: int = 50, 
                 keep_days: int = 7, compress_old: bool = True):
        # Use project logs directory if no specific directory provided
        if log_dir is None:
            project_root = Path(__file__).parent.parent.parent
            log_dir = str(project_root / "logs")
        
        self.log_dir = Path(log_dir)
        self.max_size_mb = max_size_mb
        self.keep_days = keep_days
        self.compress_old = compress_old
        
        # Ensure log directory exists
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            # Fallback to temp directory if permission denied
            import tempfile
            self.log_dir = Path(tempfile.gettempdir()) / "alisa_logs"
            self.log_dir.mkdir(parents=True, exist_ok=True)
    
    async def rotate_logs(self) -> Dict[str, Any]:
        """Rotate log files if they exceed size limit."""
        results = {
            "rotated_files": [],
            "compressed_files": [],
            "deleted_files": [],
            "total_space_freed_mb": 0
        }
        
        try:
            # Find log files that need rotation
            for log_file in self.log_dir.glob("*.log"):
                if await self._should_rotate(log_file):
                    rotated_file = await self._rotate_file(log_file)
                    results["rotated_files"].append(str(rotated_file))
                    
                    if self.compress_old:
                        compressed_file = await self._compress_file(rotated_file)
                        if compressed_file:
                            results["compressed_files"].append(str(compressed_file))
            
            # Clean up old files
            deleted_size = await self._cleanup_old_files()
            results["total_space_freed_mb"] = deleted_size / (1024 * 1024)
            
            logger.info("Log rotation completed", **results)
            
        except Exception as e:
            logger.error("Log rotation failed", error=str(e))
            results["error"] = str(e)
        
        return results
    
    async def _should_rotate(self, log_file: Path) -> bool:
        """Check if log file should be rotated."""
        try:
            size_mb = log_file.stat().st_size / (1024 * 1024)
            return size_mb > self.max_size_mb
        except (OSError, FileNotFoundError):
            return False
    
    async def _rotate_file(self, log_file: Path) -> Path:
        """Rotate a log file by adding timestamp."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        rotated_name = f"{log_file.stem}_{timestamp}.log"
        rotated_file = log_file.parent / rotated_name
        
        # Move current log to rotated name
        shutil.move(str(log_file), str(rotated_file))
        
        # Create new empty log file
        log_file.touch()
        
        logger.info("Log file rotated", original=str(log_file), rotated=str(rotated_file))
        return rotated_file
    
    async def _compress_file(self, log_file: Path) -> Optional[Path]:
        """Compress a log file with gzip."""
        try:
            compressed_file = log_file.with_suffix(log_file.suffix + ".gz")
            
            with open(log_file, 'rb') as f_in:
                with gzip.open(compressed_file, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            # Remove original file after compression
            log_file.unlink()
            
            logger.info("Log file compressed", original=str(log_file), compressed=str(compressed_file))
            return compressed_file
            
        except Exception as e:
            logger.error("Failed to compress log file", file=str(log_file), error=str(e))
            return None
    
    async def _cleanup_old_files(self) -> int:
        """Remove old log files beyond retention period."""
        cutoff_date = datetime.now() - timedelta(days=self.keep_days)
        total_size_freed = 0
        
        # Find old log files (both .log and .log.gz)
        for pattern in ["*.log", "*.log.gz"]:
            for log_file in self.log_dir.glob(pattern):
                try:
                    # Skip current log files (without timestamp)
                    if not any(char.isdigit() for char in log_file.stem):
                        continue
                    
                    file_time = datetime.fromtimestamp(log_file.stat().st_mtime)
                    if file_time < cutoff_date:
                        file_size = log_file.stat().st_size
                        log_file.unlink()
                        total_size_freed += file_size
                        logger.info("Old log file deleted", file=str(log_file))
                        
                except (OSError, FileNotFoundError) as e:
                    logger.warning("Failed to delete old log file", file=str(log_file), error=str(e))
        
        return total_size_freed
    
    async def get_log_stats(self) -> Dict[str, Any]:
        """Get statistics about log files."""
        stats = {
            "total_files": 0,
            "total_size_mb": 0,
            "current_logs": [],
            "archived_logs": [],
            "oldest_file": None,
            "newest_file": None
        }
        
        try:
            oldest_time = None
            newest_time = None
            
            for log_file in self.log_dir.glob("*"):
                if not log_file.is_file():
                    continue
                
                file_stat = log_file.stat()
                file_size_mb = file_stat.st_size / (1024 * 1024)
                file_time = datetime.fromtimestamp(file_stat.st_mtime)
                
                stats["total_files"] += 1
                stats["total_size_mb"] += file_size_mb
                
                # Track oldest and newest
                if oldest_time is None or file_time < oldest_time:
                    oldest_time = file_time
                    stats["oldest_file"] = str(log_file)
                
                if newest_time is None or file_time > newest_time:
                    newest_time = file_time
                    stats["newest_file"] = str(log_file)
                
                # Categorize files
                file_info = {
                    "name": log_file.name,
                    "size_mb": round(file_size_mb, 2),
                    "modified": file_time.isoformat()
                }
                
                if log_file.suffix == ".log" and not any(char.isdigit() for char in log_file.stem):
                    stats["current_logs"].append(file_info)
                else:
                    stats["archived_logs"].append(file_info)
            
            stats["total_size_mb"] = round(stats["total_size_mb"], 2)
            
        except Exception as e:
            logger.error("Failed to get log stats", error=str(e))
            stats["error"] = str(e)
        
        return stats


# Global instance
_log_manager = None


def get_log_manager() -> LogManager:
    """Get global log manager instance."""
    global _log_manager
    if _log_manager is None:
        _log_manager = LogManager()
    return _log_manager
