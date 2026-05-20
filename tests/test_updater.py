"""Tests for updater service."""

import pytest
from unittest.mock import patch, MagicMock
from alisa.services.updater import (
    get_git_branch,
    check_git_status,
    perform_update,
    install_dependencies,
    restart_service,
    get_current_version
)


@patch('alisa.services.updater.get_config')
def test_get_git_branch_configured(mock_get_config):
    """Test get_git_branch with configured branch."""
    mock_get_config.return_value = {
        "updater": {"git_branch": "develop"}
    }
    
    assert get_git_branch() == "develop"


@patch('alisa.services.updater.get_config')
@patch('subprocess.run')
def test_get_git_branch_auto_detect(mock_run, mock_get_config):
    """Test get_git_branch with auto-detection."""
    mock_get_config.return_value = {"updater": {"git_branch": None}}
    
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "feature-branch\n"
    mock_run.return_value = mock_result
    
    assert get_git_branch() == "feature-branch"
    
    mock_run.assert_called_once_with(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        timeout=5
    )


@patch('alisa.services.updater.get_config')
@patch('subprocess.run')
def test_get_git_branch_fallback(mock_run, mock_get_config):
    """Test get_git_branch fallback to main."""
    mock_get_config.return_value = {"updater": {"git_branch": None}}
    mock_run.side_effect = Exception("Git command failed")
    
    assert get_git_branch() == "main"


@patch('alisa.services.updater.get_git_branch')
@patch('subprocess.run')
def test_check_git_status_updates_available(mock_run, mock_get_branch):
    """Test check_git_status with updates available."""
    mock_get_branch.return_value = "main"
    
    # Mock git fetch success
    fetch_result = MagicMock()
    fetch_result.returncode = 0
    
    # Mock git status success
    status_result = MagicMock()
    status_result.returncode = 0
    
    # Mock git rev-list showing 3 commits behind
    revlist_result = MagicMock()
    revlist_result.returncode = 0
    revlist_result.stdout = "3\n"
    
    mock_run.side_effect = [fetch_result, status_result, revlist_result]
    
    success, message = check_git_status()
    
    assert success is True
    assert "3 yangi commit mavjud" in message


@patch('alisa.services.updater.get_git_branch')
@patch('subprocess.run')
def test_check_git_status_no_updates(mock_run, mock_get_branch):
    """Test check_git_status with no updates."""
    mock_get_branch.return_value = "main"
    
    # Mock successful commands with 0 commits behind
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "0\n"
    
    mock_run.side_effect = [mock_result, mock_result, mock_result]
    
    success, message = check_git_status()
    
    assert success is False
    assert "Hech qanday yangilanish yo'q" in message


@patch('alisa.services.updater.get_config')
@patch('subprocess.run')
def test_install_dependencies_configured_pip(mock_run, mock_get_config):
    """Test install_dependencies with configured pip path."""
    mock_get_config.return_value = {
        "updater": {"pip_path": "/opt/alisa/venv/bin/pip"}
    }
    
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_run.return_value = mock_result
    
    success, message = install_dependencies()
    
    assert success is True
    assert "Dependencies updated" in message
    
    mock_run.assert_called_once_with(
        ["/opt/alisa/venv/bin/pip", "install", "-r", "requirements.txt"],
        capture_output=True,
        text=True,
        timeout=300
    )


@patch('alisa.services.updater.get_config')
@patch('subprocess.run')
def test_install_dependencies_default_pip(mock_run, mock_get_config):
    """Test install_dependencies with default pip."""
    mock_get_config.return_value = {"updater": {}}
    
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_run.return_value = mock_result
    
    success, message = install_dependencies()
    
    assert success is True
    
    mock_run.assert_called_once_with(
        ["pip", "install", "-r", "requirements.txt"],
        capture_output=True,
        text=True,
        timeout=300
    )


@patch('subprocess.run')
def test_restart_service_success(mock_run):
    """Test restart_service success."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_run.return_value = mock_result
    
    success, message = restart_service()
    
    assert success is True
    assert "Service restarted" in message
    
    mock_run.assert_called_once_with(
        ["sudo", "systemctl", "restart", "alisa.service"],
        capture_output=True,
        text=True,
        timeout=30
    )


@patch('subprocess.run')
def test_restart_service_failure(mock_run):
    """Test restart_service failure."""
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "Permission denied"
    mock_run.return_value = mock_result
    
    success, message = restart_service()
    
    assert success is False
    assert "Systemctl restart failed: Permission denied" in message


@patch('subprocess.run')
def test_restart_service_sudoers_missing(mock_run):
    """Test restart_service when sudoers entry is missing."""
    # Simulate sudo asking for password (which would fail in automated context)
    mock_run.side_effect = Exception("sudo: no tty present and no askpass program specified")
    
    success, message = restart_service()
    
    assert success is False
    assert "Service restart error" in message


@patch('alisa.services.updater.get_git_branch')
@patch('alisa.services.updater.install_dependencies')
@patch('alisa.services.updater.restart_service')
@patch('subprocess.run')
def test_perform_update_success(mock_run, mock_restart, mock_install, mock_get_branch):
    """Test perform_update success."""
    mock_get_branch.return_value = "main"
    
    # Mock git status (clean working directory)
    status_result = MagicMock()
    status_result.returncode = 0
    status_result.stdout = ""
    
    # Mock git pull success
    pull_result = MagicMock()
    pull_result.returncode = 0
    pull_result.stdout = "Updated main branch"
    
    mock_run.side_effect = [status_result, pull_result]
    mock_restart.return_value = (True, "Service restarted")
    
    success, message = perform_update()
    
    assert success is True
    assert "Yangilanish muvaffaqiyatli" in message


@patch('alisa.services.updater.get_git_branch')
@patch('alisa.services.updater.install_dependencies')
@patch('alisa.services.updater.restart_service')
@patch('subprocess.run')
def test_perform_update_with_requirements_change(mock_run, mock_restart, mock_install, mock_get_branch):
    """Test perform_update when requirements.txt changes."""
    mock_get_branch.return_value = "main"
    
    # Mock git status (clean working directory)
    status_result = MagicMock()
    status_result.returncode = 0
    status_result.stdout = ""
    
    # Mock git pull with requirements.txt change
    pull_result = MagicMock()
    pull_result.returncode = 0
    pull_result.stdout = "requirements.txt updated"
    
    mock_run.side_effect = [status_result, pull_result]
    mock_install.return_value = (True, "Dependencies updated")
    mock_restart.return_value = (True, "Service restarted")
    
    success, message = perform_update()
    
    assert success is True
    mock_install.assert_called_once()


@patch('subprocess.run')
def test_get_current_version_success(mock_run):
    """Test get_current_version success."""
    # Mock git rev-parse
    hash_result = MagicMock()
    hash_result.returncode = 0
    hash_result.stdout = "abc123\n"
    
    # Mock git branch
    branch_result = MagicMock()
    branch_result.returncode = 0
    branch_result.stdout = "main\n"
    
    mock_run.side_effect = [hash_result, branch_result]
    
    version = get_current_version()
    
    assert version == "main@abc123"


@patch('subprocess.run')
def test_get_current_version_no_branch(mock_run):
    """Test get_current_version when branch command fails."""
    # Mock git rev-parse success
    hash_result = MagicMock()
    hash_result.returncode = 0
    hash_result.stdout = "abc123\n"
    
    # Mock git branch failure
    branch_result = MagicMock()
    branch_result.returncode = 1
    
    mock_run.side_effect = [hash_result, branch_result]
    
    version = get_current_version()
    
    assert version == "abc123"


@patch('subprocess.run')
def test_get_current_version_failure(mock_run):
    """Test get_current_version failure."""
    mock_run.side_effect = Exception("Git not found")
    
    version = get_current_version()
    
    assert version is None


def test_sudoers_file_exists():
    """Test that sudoers file exists and has correct content."""
    from pathlib import Path
    
    sudoers_file = Path(__file__).parent.parent / "setup" / "sudoers.d" / "alisa"
    
    assert sudoers_file.exists(), "Sudoers file should exist"
    
    content = sudoers_file.read_text()
    assert "alisa ALL=(root) NOPASSWD: /bin/systemctl restart alisa.service" in content
    assert content.strip().endswith("alisa.service"), "Should allow restarting alisa.service"


def test_install_script_has_sudoers_validation():
    """Test that install.sh validates sudoers file."""
    from pathlib import Path
    
    install_script = Path(__file__).parent.parent / "setup" / "install.sh"
    content = install_script.read_text()
    
    assert "visudo -cf" in content, "Should validate sudoers file with visudo"
    assert "/etc/sudoers.d/alisa" in content, "Should install sudoers file"
    assert "chmod 0440" in content, "Should set correct permissions on sudoers file"
