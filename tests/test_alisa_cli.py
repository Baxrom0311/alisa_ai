"""Tests for Alisa CLI utility."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


class TestAlisaCLI:
    """Test Alisa CLI commands."""
    
    def test_cli_status_command(self):
        """Test status command execution."""
        result = subprocess.run(
            [sys.executable, "alisa_cli.py", "status"],
            cwd=Path(__file__).parent.parent,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
        assert "System Status" in result.stdout
        assert "System Health" in result.stdout
        assert "Memory Pressure" in result.stdout
    
    def test_cli_config_command(self):
        """Test config command execution."""
        result = subprocess.run(
            [sys.executable, "alisa_cli.py", "config"],
            cwd=Path(__file__).parent.parent,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
        assert "Configuration" in result.stdout
        assert "Language:" in result.stdout
        assert "Wake Word:" in result.stdout
        assert "Configured Providers:" in result.stdout
    
    def test_cli_diagnose_command(self):
        """Test diagnose command execution."""
        result = subprocess.run(
            [sys.executable, "alisa_cli.py", "diagnose"],
            cwd=Path(__file__).parent.parent,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
        assert "System Diagnostics" in result.stdout
        assert "System Information" in result.stdout
        assert "Component Validation" in result.stdout
        assert "File System Check" in result.stdout
        assert "Network Check" in result.stdout
        assert "Process Check" in result.stdout
    
    def test_cli_memory_command(self):
        """Test memory command execution."""
        result = subprocess.run(
            [sys.executable, "alisa_cli.py", "memory"],
            cwd=Path(__file__).parent.parent,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
        assert "Memory Management" in result.stdout
        assert "Current Memory Usage" in result.stdout
        assert "Process RSS" in result.stdout
        assert "GC Objects" in result.stdout
    
    def test_cli_providers_command(self):
        """Test providers command execution."""
        result = subprocess.run(
            [sys.executable, "alisa_cli.py", "providers"],
            cwd=Path(__file__).parent.parent,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
        assert "LLM Providers Status" in result.stdout
    
    def test_cli_test_command(self):
        """Test test command execution."""
        result = subprocess.run(
            [sys.executable, "alisa_cli.py", "test"],
            cwd=Path(__file__).parent.parent,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
        assert "Testing Alisa Components" in result.stdout
        assert "Testing LLM" in result.stdout
        assert "Testing Config" in result.stdout
    
    def test_cli_invalid_command(self):
        """Test invalid command handling."""
        result = subprocess.run(
            [sys.executable, "alisa_cli.py", "invalid"],
            cwd=Path(__file__).parent.parent,
            capture_output=True,
            text=True
        )
        
        assert result.returncode != 0
        assert "invalid choice" in result.stderr.lower()
    
    def test_cli_help(self):
        """Test help output."""
        result = subprocess.run(
            [sys.executable, "alisa_cli.py", "--help"],
            cwd=Path(__file__).parent.parent,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
        assert "Alisa AI Assistant CLI" in result.stdout
        assert "status" in result.stdout
        assert "providers" in result.stdout
        assert "config" in result.stdout
        assert "test" in result.stdout
        assert "diagnose" in result.stdout


class TestCLIFunctions:
    """Test individual CLI functions."""
    
    def test_status_command_function(self):
        """Test status command function."""
        from alisa_cli import status_command
        
        # Should not raise exception
        status_command()
    
    def test_config_command_function(self):
        """Test config command function."""
        from alisa_cli import config_command
        
        # Should not raise exception
        config_command()
    
    def test_diagnose_command_function(self):
        """Test diagnose command function."""
        from alisa_cli import diagnose_command
        
        # Should not raise exception
        diagnose_command()
    
    def test_memory_command_function(self):
        """Test memory command function."""
        from alisa_cli import memory_command
        
        # Should not raise exception
        memory_command()
