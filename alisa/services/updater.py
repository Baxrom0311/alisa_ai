"""OTA (Over-The-Air) update service."""

import subprocess
import structlog
from pathlib import Path
from typing import Tuple, Optional

from alisa.core.config import get_config

logger = structlog.get_logger()


def get_git_branch() -> str:
    """Get current git branch or configured branch."""
    config = get_config()
    configured_branch = config.get("updater", {}).get("git_branch")
    
    if configured_branch:
        return configured_branch
    
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    
    return "main"  # fallback


def check_git_status() -> Tuple[bool, str]:
    """Check if there are updates available from git remote."""
    try:
        # Fetch latest changes
        result = subprocess.run(
            ["git", "fetch", "origin"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            return False, f"Git fetch failed: {result.stderr}"
        
        # Check if local is behind remote
        result = subprocess.run(
            ["git", "status", "-uno", "--porcelain=v1"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return False, f"Git status failed: {result.stderr}"
        
        # Check for behind status
        branch = get_git_branch()
        result = subprocess.run(
            ["git", "rev-list", "--count", f"HEAD..origin/{branch}"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return False, f"Git rev-list failed: {result.stderr}"
        
        commits_behind = int(result.stdout.strip())
        
        if commits_behind > 0:
            return True, f"{commits_behind} yangi commit mavjud"
        else:
            return False, "Hech qanday yangilanish yo'q"
            
    except subprocess.TimeoutExpired:
        return False, "Git buyruq timeout"
    except Exception as e:
        return False, f"Git xatolik: {str(e)}"


def perform_update() -> Tuple[bool, str]:
    """Perform git pull and restart service."""
    try:
        # Check if working directory is clean
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return False, f"Git status check failed: {result.stderr}"
        
        if result.stdout.strip():
            return False, "Working directory is not clean. Commit or stash changes first."
        
        # Perform git pull
        branch = get_git_branch()
        result = subprocess.run(
            ["git", "pull", "origin", branch],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0:
            return False, f"Git pull failed: {result.stderr}"
        
        logger.info("git_pull_success", output=result.stdout)
        
        # Install/update dependencies if requirements.txt changed
        if "requirements.txt" in result.stdout:
            install_result = install_dependencies()
            if not install_result[0]:
                logger.warning("dependency_install_failed", error=install_result[1])
        
        # Restart service (if running under systemd)
        restart_result = restart_service()
        if restart_result[0]:
            return True, f"Yangilanish muvaffaqiyatli: {result.stdout.strip()}"
        else:
            return True, f"Yangilanish muvaffaqiyatli, lekin restart failed: {restart_result[1]}"
            
    except subprocess.TimeoutExpired:
        return False, "Update timeout"
    except Exception as e:
        return False, f"Update xatolik: {str(e)}"


def install_dependencies() -> Tuple[bool, str]:
    """Install/update Python dependencies."""
    try:
        config = get_config()
        pip_path = config.get("updater", {}).get("pip_path", "pip")
        
        result = subprocess.run(
            [pip_path, "install", "-r", "requirements.txt"],
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes for pip install
        )
        
        if result.returncode == 0:
            logger.info("dependencies_installed")
            return True, "Dependencies updated"
        else:
            return False, f"Pip install failed: {result.stderr}"
            
    except subprocess.TimeoutExpired:
        return False, "Pip install timeout"
    except Exception as e:
        return False, f"Pip install error: {str(e)}"


def restart_service() -> Tuple[bool, str]:
    """Restart the Alisa systemd service."""
    try:
        # Try to restart via systemd
        result = subprocess.run(
            ["sudo", "systemctl", "restart", "alisa.service"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            logger.info("service_restarted")
            return True, "Service restarted"
        else:
            return False, f"Systemctl restart failed: {result.stderr}"
            
    except subprocess.TimeoutExpired:
        return False, "Service restart timeout"
    except Exception as e:
        return False, f"Service restart error: {str(e)}"


def get_current_version() -> Optional[str]:
    """Get current git commit hash and branch."""
    try:
        # Get current commit hash
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode != 0:
            return None
        
        commit_hash = result.stdout.strip()
        
        # Get current branch
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode != 0:
            return commit_hash
        
        branch = result.stdout.strip()
        return f"{branch}@{commit_hash}"
        
    except Exception:
        return None
