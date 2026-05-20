"""Raspberry Pi optimization utility for Alisa AI Assistant."""

import asyncio
import logging
import os
import subprocess
import psutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class PiOptimizer:
    """Raspberry Pi system optimization utility."""
    
    def __init__(self):
        self.optimizations_applied = []
        self.original_values = {}
    
    async def analyze_system(self) -> Dict:
        """Analyze system for optimization opportunities."""
        analysis = {
            "cpu_info": self._get_cpu_info(),
            "memory_info": self._get_memory_info(),
            "swap_info": self._get_swap_info(),
            "gpu_memory": self._get_gpu_memory(),
            "thermal_info": self._get_thermal_info(),
            "recommendations": []
        }
        
        # Generate recommendations
        analysis["recommendations"] = self._generate_recommendations(analysis)
        return analysis
    
    def _get_cpu_info(self) -> Dict:
        """Get CPU information."""
        try:
            cpu_info = {
                "cores": psutil.cpu_count(logical=False),
                "threads": psutil.cpu_count(logical=True),
                "frequency": psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None,
                "usage": psutil.cpu_percent(interval=1)
            }
            
            # Try to get Pi-specific info
            try:
                with open("/proc/cpuinfo", "r") as f:
                    cpuinfo = f.read()
                    if "Raspberry Pi" in cpuinfo:
                        cpu_info["model"] = "Raspberry Pi"
                        if "BCM2711" in cpuinfo:
                            cpu_info["chip"] = "BCM2711 (Pi 4)"
                        elif "BCM2712" in cpuinfo:
                            cpu_info["chip"] = "BCM2712 (Pi 5)"
            except:
                pass
                
            return cpu_info
        except Exception as e:
            logger.warning(f"Failed to get CPU info: {e}")
            return {}
    
    def _get_memory_info(self) -> Dict:
        """Get memory information."""
        try:
            mem = psutil.virtual_memory()
            return {
                "total_gb": round(mem.total / (1024**3), 2),
                "available_gb": round(mem.available / (1024**3), 2),
                "used_percent": mem.percent,
                "free_gb": round(mem.free / (1024**3), 2)
            }
        except Exception as e:
            logger.warning(f"Failed to get memory info: {e}")
            return {}
    
    def _get_swap_info(self) -> Dict:
        """Get swap information."""
        try:
            swap = psutil.swap_memory()
            return {
                "total_gb": round(swap.total / (1024**3), 2),
                "used_gb": round(swap.used / (1024**3), 2),
                "percent": swap.percent
            }
        except Exception as e:
            logger.warning(f"Failed to get swap info: {e}")
            return {}
    
    def _get_gpu_memory(self) -> Optional[int]:
        """Get GPU memory split (Pi-specific)."""
        try:
            result = subprocess.run(
                ["vcgencmd", "get_mem", "gpu"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                # Output format: "gpu=64M"
                gpu_mem = result.stdout.strip().split("=")[1].rstrip("M")
                return int(gpu_mem)
        except:
            pass
        return None
    
    def _get_thermal_info(self) -> Dict:
        """Get thermal information."""
        thermal_info = {}
        
        try:
            # CPU temperature
            temps = psutil.sensors_temperatures()
            if temps:
                for name, entries in temps.items():
                    for entry in entries:
                        if entry.current:
                            thermal_info[f"{name}_temp"] = entry.current
            
            # Pi-specific temperature
            try:
                result = subprocess.run(
                    ["vcgencmd", "measure_temp"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    # Output format: "temp=45.1'C"
                    temp_str = result.stdout.strip().split("=")[1].rstrip("'C")
                    thermal_info["pi_temp"] = float(temp_str)
            except:
                pass
                
        except Exception as e:
            logger.warning(f"Failed to get thermal info: {e}")
            
        return thermal_info
    
    def _generate_recommendations(self, analysis: Dict) -> List[Dict]:
        """Generate optimization recommendations."""
        recommendations = []
        
        # Memory recommendations
        memory_info = analysis.get("memory_info", {})
        if memory_info.get("used_percent", 0) > 80:
            recommendations.append({
                "category": "memory",
                "priority": "high",
                "title": "High memory usage detected",
                "description": "Consider reducing memory usage or adding swap",
                "action": "optimize_memory"
            })
        
        # GPU memory recommendations
        gpu_memory = analysis.get("gpu_memory")
        if gpu_memory and gpu_memory > 128:
            recommendations.append({
                "category": "gpu",
                "priority": "medium", 
                "title": "GPU memory can be reduced",
                "description": f"GPU has {gpu_memory}MB, can reduce to 64MB for headless operation",
                "action": "reduce_gpu_memory"
            })
        
        # Thermal recommendations
        thermal_info = analysis.get("thermal_info", {})
        max_temp = max(thermal_info.values()) if thermal_info else 0
        if max_temp > 70:
            recommendations.append({
                "category": "thermal",
                "priority": "high",
                "title": "High temperature detected",
                "description": f"Temperature is {max_temp}°C, consider cooling solutions",
                "action": "thermal_management"
            })
        
        # Swap recommendations
        swap_info = analysis.get("swap_info", {})
        if swap_info.get("total_gb", 0) < 1:
            recommendations.append({
                "category": "swap",
                "priority": "medium",
                "title": "Low swap space",
                "description": "Consider adding swap file for memory stability",
                "action": "add_swap"
            })
        
        return recommendations
    
    async def apply_optimizations(self, optimizations: List[str]) -> Dict:
        """Apply selected optimizations."""
        results = {"applied": [], "failed": [], "warnings": []}
        
        for optimization in optimizations:
            try:
                if optimization == "optimize_memory":
                    await self._optimize_memory()
                    results["applied"].append("Memory optimization")
                elif optimization == "reduce_gpu_memory":
                    await self._reduce_gpu_memory()
                    results["applied"].append("GPU memory reduction")
                elif optimization == "add_swap":
                    await self._add_swap()
                    results["applied"].append("Swap file creation")
                elif optimization == "thermal_management":
                    await self._optimize_thermal()
                    results["applied"].append("Thermal optimization")
                else:
                    results["warnings"].append(f"Unknown optimization: {optimization}")
            except Exception as e:
                logger.error(f"Failed to apply {optimization}: {e}")
                results["failed"].append(f"{optimization}: {str(e)}")
        
        return results
    
    async def _optimize_memory(self):
        """Apply memory optimizations."""
        # Reduce swappiness
        try:
            subprocess.run(["sudo", "sysctl", "vm.swappiness=10"], check=True)
            self.optimizations_applied.append("swappiness")
        except subprocess.CalledProcessError:
            logger.warning("Failed to set swappiness")
        
        # Clear caches
        try:
            subprocess.run(["sudo", "sync"], check=True)
            subprocess.run(["sudo", "sh", "-c", "echo 1 > /proc/sys/vm/drop_caches"], check=True)
        except subprocess.CalledProcessError:
            logger.warning("Failed to clear caches")
    
    async def _reduce_gpu_memory(self):
        """Reduce GPU memory allocation."""
        config_path = Path("/boot/config.txt")
        if not config_path.exists():
            config_path = Path("/boot/firmware/config.txt")  # Pi 5
        
        if config_path.exists():
            try:
                # Read current config
                with open(config_path, "r") as f:
                    lines = f.readlines()
                
                # Update or add gpu_mem setting
                gpu_mem_set = False
                for i, line in enumerate(lines):
                    if line.startswith("gpu_mem="):
                        lines[i] = "gpu_mem=64\n"
                        gpu_mem_set = True
                        break
                
                if not gpu_mem_set:
                    lines.append("gpu_mem=64\n")
                
                # Write back (requires sudo)
                with open("/tmp/config.txt", "w") as f:
                    f.writelines(lines)
                
                subprocess.run(["sudo", "cp", "/tmp/config.txt", str(config_path)], check=True)
                self.optimizations_applied.append("gpu_memory")
                
            except Exception as e:
                logger.error(f"Failed to update GPU memory: {e}")
                raise
    
    async def _add_swap(self):
        """Add swap file."""
        swap_file = Path("/swapfile")
        if swap_file.exists():
            logger.info("Swap file already exists")
            return
        
        try:
            # Create 1GB swap file
            subprocess.run(["sudo", "fallocate", "-l", "1G", "/swapfile"], check=True)
            subprocess.run(["sudo", "chmod", "600", "/swapfile"], check=True)
            subprocess.run(["sudo", "mkswap", "/swapfile"], check=True)
            subprocess.run(["sudo", "swapon", "/swapfile"], check=True)
            
            # Add to fstab
            with open("/tmp/fstab_append", "w") as f:
                f.write("/swapfile none swap sw 0 0\n")
            subprocess.run(["sudo", "sh", "-c", "cat /tmp/fstab_append >> /etc/fstab"], check=True)
            
            self.optimizations_applied.append("swap_file")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create swap: {e}")
            raise
    
    async def _optimize_thermal(self):
        """Apply thermal optimizations."""
        # Enable thermal throttling protection
        try:
            subprocess.run(["sudo", "sysctl", "kernel.printk=3"], check=True)
            self.optimizations_applied.append("thermal_throttling")
        except subprocess.CalledProcessError:
            logger.warning("Failed to set thermal throttling")
    
    def get_optimization_status(self) -> Dict:
        """Get current optimization status."""
        return {
            "applied_optimizations": self.optimizations_applied,
            "original_values": self.original_values,
            "timestamp": psutil.boot_time()
        }


# Global instance
_pi_optimizer = None

def get_pi_optimizer() -> PiOptimizer:
    """Get global Pi optimizer instance."""
    global _pi_optimizer
    if _pi_optimizer is None:
        _pi_optimizer = PiOptimizer()
    return _pi_optimizer
