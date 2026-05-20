"""Configuration and system validation for Alisa AI Assistant."""

import subprocess
import shutil
from pathlib import Path
from typing import Dict, List, Tuple

import structlog

from alisa.core.config import get_config

logger = structlog.get_logger()


def validate_system() -> Tuple[bool, List[str]]:
    """Validate system configuration and dependencies."""
    config = get_config()
    issues = []
    
    # Check external binaries
    whisper_binary = config["whisper"]["binary"]
    if not shutil.which(whisper_binary) and not Path(whisper_binary).exists():
        issues.append(f"Whisper binary not found: {whisper_binary}")
    
    piper_binary = config["piper"]["binary"]
    if not shutil.which(piper_binary) and not Path(piper_binary).exists():
        issues.append(f"Piper binary not found: {piper_binary}")
    
    # Check model files
    whisper_model = Path(config["whisper"]["model"])
    if not whisper_model.exists():
        issues.append(f"Whisper model not found: {whisper_model}")
    
    piper_model = Path(config["piper"]["model"])
    if not piper_model.exists():
        issues.append(f"Piper model not found: {piper_model}")
    
    # Check Ollama connection
    try:
        import httpx
        ollama_url = config["ollama"]["url"]
        resp = httpx.get(f"{ollama_url}/api/tags", timeout=5.0)
        if resp.status_code != 200:
            issues.append(f"Ollama not responding at {ollama_url}")
    except Exception as e:
        issues.append(f"Ollama connection failed: {e}")
    
    # Check output directories
    piper_output = Path(config["piper"]["output_dir"])
    if not piper_output.exists():
        try:
            piper_output.mkdir(parents=True, exist_ok=True)
            logger.info("created_output_dir", path=str(piper_output))
        except Exception as e:
            issues.append(f"Cannot create output directory {piper_output}: {e}")
    
    # Check Telegram configuration if tokens are provided
    if config["telegram"]["bot_token"] and not config["telegram"]["chat_id"]:
        issues.append("Telegram bot token provided but chat_id missing")
    
    is_valid = len(issues) == 0
    
    if is_valid:
        logger.info("system_validation_passed")
    else:
        logger.warning("system_validation_failed", issues=issues)
    
    return is_valid, issues


def get_system_info() -> Dict[str, str]:
    """Get system information for diagnostics."""
    info = {}
    
    try:
        # Python version
        import sys
        info["python_version"] = sys.version.split()[0]
        
        # OS info
        import platform
        info["os"] = platform.system()
        info["architecture"] = platform.machine()
        
        # Memory info (Linux only)
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        info["total_memory"] = line.split()[1] + " kB"
                        break
        except FileNotFoundError:
            info["total_memory"] = "unknown"
        
        # Disk space
        import shutil
        total, used, free = shutil.disk_usage("/")
        info["disk_free"] = f"{free // (1024**3)} GB"
        
        # Git info
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                info["git_commit"] = result.stdout.strip()
        except Exception:
            info["git_commit"] = "unknown"
        
    except Exception as e:
        logger.error("system_info_error", error=str(e))
    
    return info
