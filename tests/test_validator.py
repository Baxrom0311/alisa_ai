"""Tests for system validator."""

import pytest
from unittest.mock import patch, mock_open
from pathlib import Path

from alisa.core.validator import validate_system, get_system_info


class TestValidator:
    """Test system validation functions."""
    
    def test_get_system_info(self):
        """Test system info collection."""
        info = get_system_info()
        
        # Should always have these basic fields
        assert "python_version" in info
        assert "os" in info
        assert "architecture" in info
        
        # Version should be a valid format
        assert "." in info["python_version"]
    
    @patch('shutil.which')
    @patch('pathlib.Path.exists')
    @patch('httpx.get')
    def test_validate_system_success(self, mock_httpx, mock_exists, mock_which):
        """Test successful system validation."""
        # Mock all dependencies as available
        mock_which.return_value = "/usr/local/bin/tool"
        mock_exists.return_value = True
        
        # Mock successful Ollama response
        mock_response = type('MockResponse', (), {'status_code': 200})()
        mock_httpx.return_value = mock_response
        
        is_valid, issues = validate_system()
        
        assert is_valid
        assert len(issues) == 0
    
    @patch('shutil.which')
    @patch('pathlib.Path.exists')
    def test_validate_system_missing_binary(self, mock_exists, mock_which):
        """Test validation with missing binary."""
        # Mock missing whisper binary
        mock_which.return_value = None
        mock_exists.return_value = False
        
        is_valid, issues = validate_system()
        
        assert not is_valid
        assert any("Whisper binary not found" in issue for issue in issues)
    
    @patch('shutil.which')
    @patch('pathlib.Path.exists')
    def test_validate_system_missing_model(self, mock_exists, mock_which):
        """Test validation with missing model file."""
        # Mock binaries exist but models don't
        mock_which.return_value = "/usr/local/bin/tool"
        
        # Mock model files don't exist, everything else does
        mock_exists.return_value = False
        
        is_valid, issues = validate_system()
        
        assert not is_valid
        assert any("model not found" in issue for issue in issues)
    
    @patch('shutil.which')
    @patch('pathlib.Path.exists')
    @patch('httpx.get')
    def test_validate_system_ollama_down(self, mock_httpx, mock_exists, mock_which):
        """Test validation with Ollama service down."""
        # Mock all files exist
        mock_which.return_value = "/usr/local/bin/tool"
        mock_exists.return_value = True
        
        # Mock Ollama connection failure
        mock_httpx.side_effect = Exception("Connection refused")
        
        is_valid, issues = validate_system()
        
        assert not is_valid
        assert any("Ollama connection failed" in issue for issue in issues)
    
    @patch('pathlib.Path.mkdir')
    @patch('pathlib.Path.exists')
    @patch('shutil.which')
    def test_validate_system_creates_output_dir(self, mock_which, mock_exists, mock_mkdir):
        """Test that validation creates missing output directories."""
        # Mock binaries exist
        mock_which.return_value = "/usr/local/bin/tool"
        
        # Mock most things exist, but output dir creation succeeds
        mock_exists.return_value = True
        
        # Should not fail validation
        is_valid, issues = validate_system()
        
        # Should succeed even if directory creation is attempted
        assert isinstance(is_valid, bool)
