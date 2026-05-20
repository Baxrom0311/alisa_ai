"""System optimization utilities for Raspberry Pi deployment."""

import asyncio
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class SystemOptimizer:
    """System optimization utilities for Pi performance."""
    
    def __init__(self):
        self.optimizations = {
            "memory": self._optimize_memory,
            "swap": self._optimize_swap,
            "cpu": self._optimize_cpu,
            "disk": self._optimize_disk,
            "network": self._optimize_network
        }
    
    async def analyze_system(self) -> Dict:
        """Analyze system for optimization opportunities."""
        analysis = {
            "memory": await self._analyze_memory(),
            "swap": await self._analyze_swap(),
            "cpu": await self._analyze_cpu(),
            "disk": await self._analyze_disk(),
            "network": await self._analyze_network(),
            "recommendations": []
        }
        
        # Generate recommendations
        analysis["recommendations"] = self._generate_recommendations(analysis)
        
        return analysis
    
    async def apply_optimizations(self, categories: Optional[List[str]] = None) -> Dict:
        """Apply system optimizations."""
        if categories is None:
            categories = list(self.optimizations.keys())
        
        results = {}
        
        for category in categories:
            if category in self.optimizations:
                try:
                    logger.info(f"Applying {category} optimizations...")
                    # Get the method and call it
                    optimization_method = self.optimizations[category]
                    result = await optimization_method()
                    results[category] = {"status": "success", "result": result}
                except Exception as e:
                    logger.error(f"Failed to optimize {category}: {e}")
                    results[category] = {"status": "error", "error": str(e)}
            else:
                results[category] = {"status": "error", "error": f"Unknown optimization category: {category}"}
        
        return results
    
    async def _analyze_memory(self) -> Dict:
        """Analyze memory usage and fragmentation."""
        try:
            # Get memory info
            with open("/proc/meminfo", "r") as f:
                meminfo = f.read()
            
            memory_data = {}
            for line in meminfo.split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    memory_data[key.strip()] = value.strip()
            
            # Calculate key metrics
            total_kb = int(memory_data.get("MemTotal", "0").split()[0])
            available_kb = int(memory_data.get("MemAvailable", "0").split()[0])
            buffers_kb = int(memory_data.get("Buffers", "0").split()[0])
            cached_kb = int(memory_data.get("Cached", "0").split()[0])
            
            usage_percent = ((total_kb - available_kb) / total_kb) * 100
            cache_percent = ((buffers_kb + cached_kb) / total_kb) * 100
            
            return {
                "total_mb": total_kb // 1024,
                "available_mb": available_kb // 1024,
                "usage_percent": round(usage_percent, 1),
                "cache_percent": round(cache_percent, 1),
                "fragmentation": "low" if cache_percent > 10 else "high"
            }
        except Exception as e:
            logger.error(f"Memory analysis failed: {e}")
            return {"error": str(e)}
    
    async def _analyze_swap(self) -> Dict:
        """Analyze swap usage and configuration."""
        try:
            # Check swap usage
            with open("/proc/swaps", "r") as f:
                swaps = f.read().strip().split("\n")[1:]  # Skip header
            
            swap_info = []
            total_swap = 0
            used_swap = 0
            
            for swap_line in swaps:
                if swap_line.strip():
                    parts = swap_line.split()
                    filename = parts[0]
                    size_kb = int(parts[2])
                    used_kb = int(parts[3])
                    
                    swap_info.append({
                        "file": filename,
                        "size_mb": size_kb // 1024,
                        "used_mb": used_kb // 1024,
                        "usage_percent": round((used_kb / size_kb) * 100, 1) if size_kb > 0 else 0
                    })
                    
                    total_swap += size_kb
                    used_swap += used_kb
            
            # Check swappiness
            swappiness = 60  # default
            try:
                with open("/proc/sys/vm/swappiness", "r") as f:
                    swappiness = int(f.read().strip())
            except:
                pass
            
            return {
                "total_mb": total_swap // 1024,
                "used_mb": used_swap // 1024,
                "usage_percent": round((used_swap / total_swap) * 100, 1) if total_swap > 0 else 0,
                "swappiness": swappiness,
                "swap_files": swap_info
            }
        except Exception as e:
            logger.error(f"Swap analysis failed: {e}")
            return {"error": str(e)}
    
    async def _analyze_cpu(self) -> Dict:
        """Analyze CPU configuration and governor."""
        try:
            cpu_info = {}
            
            # Get CPU governor
            governor_path = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"
            if os.path.exists(governor_path):
                with open(governor_path, "r") as f:
                    cpu_info["governor"] = f.read().strip()
            
            # Get available governors
            governors_path = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors"
            if os.path.exists(governors_path):
                with open(governors_path, "r") as f:
                    cpu_info["available_governors"] = f.read().strip().split()
            
            # Get CPU frequency info
            freq_path = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"
            if os.path.exists(freq_path):
                with open(freq_path, "r") as f:
                    freq_str = f.read().strip()
                    try:
                        cpu_info["current_freq_khz"] = int(freq_str)
                    except ValueError:
                        # Skip if frequency is not a valid integer
                        pass
            
            # Get CPU count
            cpu_info["cpu_count"] = os.cpu_count()
            
            return cpu_info
        except Exception as e:
            logger.error(f"CPU analysis failed: {e}")
            return {"error": str(e)}
    
    async def _analyze_disk(self) -> Dict:
        """Analyze disk usage and I/O patterns."""
        try:
            import shutil
            
            # Get disk usage for root partition
            total, used, free = shutil.disk_usage("/")
            
            disk_info = {
                "total_gb": round(total / (1024**3), 2),
                "used_gb": round(used / (1024**3), 2),
                "free_gb": round(free / (1024**3), 2),
                "usage_percent": round((used / total) * 100, 1)
            }
            
            # Check if we're on SD card (common for Pi)
            try:
                with open("/proc/mounts", "r") as f:
                    mounts = f.read()
                    if "mmcblk" in mounts:
                        disk_info["storage_type"] = "sd_card"
                    else:
                        disk_info["storage_type"] = "other"
            except:
                disk_info["storage_type"] = "unknown"
            
            return disk_info
        except Exception as e:
            logger.error(f"Disk analysis failed: {e}")
            return {"error": str(e)}
    
    async def _analyze_network(self) -> Dict:
        """Analyze network configuration."""
        try:
            network_info = {}
            
            # Check network interfaces
            interfaces = []
            net_path = Path("/sys/class/net")
            if net_path.exists():
                for iface in net_path.iterdir():
                    if iface.name not in ["lo"]:  # Skip loopback
                        interfaces.append(iface.name)
            
            network_info["interfaces"] = interfaces
            
            # Check if WiFi power management is enabled
            wifi_pm_status = {}
            for iface in interfaces:
                if "wlan" in iface or "wifi" in iface:
                    try:
                        result = subprocess.run(
                            ["iwconfig", iface], 
                            capture_output=True, 
                            text=True, 
                            timeout=5
                        )
                        if "Power Management:on" in result.stdout:
                            wifi_pm_status[iface] = "on"
                        elif "Power Management:off" in result.stdout:
                            wifi_pm_status[iface] = "off"
                    except:
                        pass
            
            network_info["wifi_power_management"] = wifi_pm_status
            
            return network_info
        except Exception as e:
            logger.error(f"Network analysis failed: {e}")
            return {"error": str(e)}
    
    def _generate_recommendations(self, analysis: Dict) -> List[str]:
        """Generate optimization recommendations based on analysis."""
        recommendations = []
        
        # Memory recommendations
        memory = analysis.get("memory", {})
        if memory.get("usage_percent", 0) > 80:
            recommendations.append("High memory usage detected - consider enabling zram compression")
        if memory.get("cache_percent", 0) < 5:
            recommendations.append("Low cache usage - system may benefit from more aggressive caching")
        
        # Swap recommendations
        swap = analysis.get("swap", {})
        if swap.get("swappiness", 60) > 10:
            recommendations.append("High swappiness detected - consider reducing to 1-10 for better performance")
        if swap.get("usage_percent", 0) > 50:
            recommendations.append("High swap usage - consider adding more RAM or optimizing memory usage")
        
        # CPU recommendations
        cpu = analysis.get("cpu", {})
        if cpu.get("governor") == "powersave":
            recommendations.append("CPU governor set to powersave - consider 'ondemand' for better performance")
        
        # Disk recommendations
        disk = analysis.get("disk", {})
        if disk.get("usage_percent", 0) > 85:
            recommendations.append("Disk usage high - consider cleaning up logs and temporary files")
        if disk.get("storage_type") == "sd_card":
            recommendations.append("SD card detected - enable log rotation and minimize writes")
        
        # Network recommendations
        network = analysis.get("network", {})
        wifi_pm = network.get("wifi_power_management", {})
        if any(status == "on" for status in wifi_pm.values()):
            recommendations.append("WiFi power management enabled - consider disabling for stable connections")
        
        return recommendations
    
    async def _optimize_memory(self) -> Dict:
        """Apply memory optimizations."""
        optimizations = []
        
        try:
            # Clear page cache (safe operation)
            subprocess.run(["sync"], check=True, timeout=10)
            optimizations.append("Synced filesystem")
        except Exception as e:
            logger.warning(f"Failed to sync filesystem: {e}")
        
        try:
            # Clear page cache
            if os.path.exists("/proc/sys/vm/drop_caches"):
                with open("/proc/sys/vm/drop_caches", "w") as f:
                    f.write("1")
                optimizations.append("Cleared page cache")
            else:
                optimizations.append("Page cache clear not available (not Linux)")
        except Exception as e:
            logger.warning(f"Failed to clear page cache: {e}")
        
        return {"applied": optimizations}
    
    async def _optimize_swap(self) -> Dict:
        """Apply swap optimizations."""
        optimizations = []
        
        try:
            # Set swappiness to 1 (minimal swapping)
            with open("/proc/sys/vm/swappiness", "w") as f:
                f.write("1")
            optimizations.append("Set swappiness to 1")
        except Exception as e:
            logger.warning(f"Failed to set swappiness: {e}")
        
        return {"applied": optimizations}
    
    async def _optimize_cpu(self) -> Dict:
        """Apply CPU optimizations."""
        optimizations = []
        
        try:
            # Set CPU governor to ondemand if available
            governor_path = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"
            if os.path.exists(governor_path):
                with open(governor_path, "w") as f:
                    f.write("ondemand")
                optimizations.append("Set CPU governor to ondemand")
        except Exception as e:
            logger.warning(f"Failed to set CPU governor: {e}")
        
        return {"applied": optimizations}
    
    async def _optimize_disk(self) -> Dict:
        """Apply disk optimizations."""
        optimizations = []
        
        try:
            # Enable noatime for root filesystem (reduces SD card writes)
            # This would require remounting, so we just recommend it
            optimizations.append("Recommend enabling noatime mount option")
        except Exception as e:
            logger.warning(f"Disk optimization failed: {e}")
        
        return {"applied": optimizations}
    
    async def _optimize_network(self) -> Dict:
        """Apply network optimizations."""
        optimizations = []
        
        try:
            # Disable WiFi power management
            result = subprocess.run(
                ["iwconfig"], 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            
            # Find WiFi interfaces
            for line in result.stdout.split("\n"):
                if "IEEE 802.11" in line:
                    iface = line.split()[0]
                    try:
                        subprocess.run(
                            ["iwconfig", iface, "power", "off"], 
                            check=True, 
                            timeout=5
                        )
                        optimizations.append(f"Disabled power management for {iface}")
                    except:
                        pass
        except Exception as e:
            logger.warning(f"Network optimization failed: {e}")
        
        return {"applied": optimizations}


# Global instance
_optimizer = None

def get_optimizer() -> SystemOptimizer:
    """Get global optimizer instance."""
    global _optimizer
    if _optimizer is None:
        _optimizer = SystemOptimizer()
    return _optimizer
