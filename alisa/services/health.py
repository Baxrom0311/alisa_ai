"""System health monitoring for Raspberry Pi."""

import psutil
import structlog
import time
from pathlib import Path
from typing import Dict, Any

logger = structlog.get_logger()


def get_system_stats() -> Dict[str, Any]:
    """Get current system statistics."""
    try:
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_used_mb = memory.used // (1024 * 1024)
        memory_total_mb = memory.total // (1024 * 1024)
        
        # Disk usage
        disk = psutil.disk_usage('/')
        disk_percent = (disk.used / disk.total) * 100
        disk_free_gb = disk.free // (1024 * 1024 * 1024)
        
        # Temperature (Raspberry Pi specific)
        temp_celsius = get_cpu_temperature()
        
        # Load average
        load_avg = psutil.getloadavg()
        
        # Swap usage (important for SD card health)
        swap = psutil.swap_memory()
        swap_percent = swap.percent
        swap_used_mb = swap.used // (1024 * 1024)
        swap_total_mb = swap.total // (1024 * 1024)
        
        # Uptime
        uptime_seconds = psutil.boot_time()
        current_time = time.time()
        uptime_hours = (current_time - uptime_seconds) / 3600
        
        stats = {
            "cpu_percent": round(cpu_percent, 1),
            "memory_percent": round(memory_percent, 1),
            "memory_used_mb": memory_used_mb,
            "memory_total_mb": memory_total_mb,
            "disk_percent": round(disk_percent, 1),
            "disk_free_gb": disk_free_gb,
            "temperature_c": temp_celsius,
            "load_avg_1m": round(load_avg[0], 2),
            "load_avg_5m": round(load_avg[1], 2),
            "load_avg_15m": round(load_avg[2], 2),
            "swap_percent": round(swap_percent, 1),
            "swap_used_mb": swap_used_mb,
            "swap_total_mb": swap_total_mb,
            "uptime_hours": round(uptime_hours, 1),
        }
        
        logger.info("system_stats_collected", **stats)
        return stats
        
    except Exception as e:
        logger.error("system_stats_error", error=str(e))
        return {}


def get_cpu_temperature() -> float:
    """Get CPU temperature on Raspberry Pi."""
    try:
        # Try Raspberry Pi thermal zone
        thermal_file = Path("/sys/class/thermal/thermal_zone0/temp")
        if thermal_file.exists():
            temp_str = thermal_file.read_text().strip()
            temp_celsius = int(temp_str) / 1000.0
            return round(temp_celsius, 1)
    except Exception:
        pass
    
    try:
        # Try vcgencmd (Raspberry Pi specific)
        import subprocess
        result = subprocess.run(
            ["vcgencmd", "measure_temp"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0:
            # Output format: temp=45.1'C
            temp_str = result.stdout.strip()
            temp_celsius = float(temp_str.split('=')[1].replace("'C", ""))
            return round(temp_celsius, 1)
    except Exception:
        pass
    
    # Fallback - no temperature available
    return 0.0


def format_system_status() -> str:
    """Format system status for human reading."""
    stats = get_system_stats()
    if not stats:
        return "Tizim holati ma'lumotlari olinmadi."
    
    status_lines = [
        f"🖥️ CPU: {stats['cpu_percent']}%",
        f"🧠 RAM: {stats['memory_used_mb']}MB / {stats['memory_total_mb']}MB ({stats['memory_percent']}%)",
        f"💾 Disk: {stats['disk_free_gb']}GB bo'sh ({100-stats['disk_percent']:.1f}%)",
        f"🔄 Swap: {stats['swap_used_mb']}MB / {stats['swap_total_mb']}MB ({stats['swap_percent']}%)",
        f"🌡️ Harorat: {stats['temperature_c']}°C",
        f"⚡ Load: {stats['load_avg_1m']} / {stats['load_avg_5m']} / {stats['load_avg_15m']}"
    ]
    
    return "\n".join(status_lines)


def is_system_healthy() -> bool:
    """Check if system is in healthy state."""
    stats = get_system_stats()
    if not stats:
        return False
    
    # Health thresholds for Raspberry Pi
    if stats['cpu_percent'] > 90:
        logger.warning("high_cpu_usage", cpu=stats['cpu_percent'])
        return False
    
    if stats['memory_percent'] > 85:
        logger.warning("high_memory_usage", memory=stats['memory_percent'])
        return False
    
    if stats['temperature_c'] > 80:
        logger.warning("high_temperature", temp=stats['temperature_c'])
        return False
    
    if stats['disk_percent'] > 90:
        logger.warning("low_disk_space", disk=stats['disk_percent'])
        return False
    
    # Check swap usage (high swap usage can wear out SD card)
    if stats['swap_percent'] > 50:
        logger.warning("high_swap_usage", swap=stats['swap_percent'])
        return False
    
    return True


def check_memory_pressure() -> dict:
    """Check memory pressure and suggest actions for Pi optimization."""
    try:
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        available_mb = memory.available / (1024 * 1024)
        
        pressure_level = "normal"
        suggestions = []
        
        # Check swap usage first (SD card health concern)
        if swap.percent > 25:
            pressure_level = "high"
            suggestions.append("High swap usage detected - may wear SD card")
            suggestions.append("Consider increasing RAM or reducing memory usage")
        
        if available_mb < 200:  # Less than 200MB available
            pressure_level = "critical"
            suggestions.extend([
                "Consider restarting Alisa to free memory",
                "Check for memory leaks in running processes",
                "Reduce Ollama model size if possible"
            ])
        elif available_mb < 500:  # Less than 500MB available
            if pressure_level != "high":  # Don't downgrade from swap warning
                pressure_level = "high"
            suggestions.extend([
                "Monitor memory usage closely",
                "Consider clearing conversation memory",
                "Avoid running additional processes"
            ])
        elif available_mb < 1000:  # Less than 1GB available
            if pressure_level == "normal":  # Don't downgrade from higher levels
                pressure_level = "moderate"
                suggestions.append("Memory usage is elevated but manageable")
        
        return {
            "pressure_level": pressure_level,
            "available_mb": round(available_mb, 1),
            "swap_percent": round(swap.percent, 1),
            "suggestions": suggestions,
            "memory_percent": memory.percent
        }
    
    except Exception as e:
        logger.error("memory_pressure_check_failed", error=str(e))
        return {
            "pressure_level": "unknown",
            "available_mb": 0,
            "swap_percent": 0,
            "suggestions": ["Unable to check memory pressure"],
            "memory_percent": 0
        }
