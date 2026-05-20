"""Tests for setup configuration and install script."""

import pytest
import yaml
from pathlib import Path
from alisa.core.config import get_config

class TestSetupConfig:
    """Test setup configuration and schema."""
    
    def test_config_yaml_example_exists(self):
        """Test that config.yaml.example exists."""
        config_example = Path(__file__).parent.parent / "config.yaml.example"
        assert config_example.exists(), "config.yaml.example should exist"
    
    def test_config_yaml_example_schema(self):
        """Test that config.yaml.example has all required keys."""
        config_example = Path(__file__).parent.parent / "config.yaml.example"
        with open(config_example) as f:
            config = yaml.safe_load(f)
        
        # Check all required top-level keys
        required_keys = [
            "whisper", "piper", "ollama", "audio", 
            "wake_word", "telegram", "reception", "scheduler"
        ]
        for key in required_keys:
            assert key in config, f"config.yaml.example missing key: {key}"
        
        # Check whisper section
        assert "binary" in config["whisper"]
        assert "model" in config["whisper"]
        assert "language" in config["whisper"]
        
        # Check piper section
        assert "binary" in config["piper"]
        assert "model" in config["piper"]
        assert "output_dir" in config["piper"]
        
        # Check model paths match what install.sh downloads
        assert config["whisper"]["model"].endswith("ggml-base.bin")  # Uzbek uses base model
        assert "uz_UZ-doniyorbek-medium.onnx" in config["piper"]["model"] or "ru_RU-irina-medium.onnx" in config["piper"]["model"]  # Uzbek or Russian fallback
        assert config["whisper"]["language"] == "uz"  # Uzbek language
    
    def test_current_config_matches_schema(self):
        """Test that current config.yaml matches expected schema."""
        config = get_config()
        
        # Check that piper model path exists in config and matches downloaded file
        piper_model = config["piper"]["model"]
        assert "uz_UZ-doniyorbek-medium.onnx" in piper_model or "ru_RU-irina-medium.onnx" in piper_model, f"Piper model should be Uzbek or Russian fallback, got: {piper_model}"
        
        # Check whisper model path
        whisper_model = config["whisper"]["model"]
        assert "ggml-base.bin" in whisper_model, f"Whisper model should be ggml-base.bin, got: {whisper_model}"
        
        # Check language setting
        assert config["whisper"]["language"] == "uz", f"Whisper language should be 'uz', got: {config['whisper']['language']}"
    
    def test_install_script_exists(self):
        """Test that install.sh exists and is executable."""
        install_script = Path(__file__).parent.parent / "setup" / "install.sh"
        assert install_script.exists(), "setup/install.sh should exist"
        assert install_script.stat().st_mode & 0o111, "install.sh should be executable"
    
    def test_systemd_service_exists(self):
        """Test that systemd service file exists."""
        service_file = Path(__file__).parent.parent / "setup" / "systemd" / "alisa.service"
        assert service_file.exists(), "setup/systemd/alisa.service should exist"
    
    def test_install_sh_mkdir_before_tee(self):
        """Test that mkdir -p /etc/alisa comes before tee /etc/alisa/environment."""
        install_script = Path(__file__).parent.parent / "setup" / "install.sh"
        with open(install_script) as f:
            lines = f.readlines()
        
        mkdir_line_idx = None
        tee_line_idx = None
        
        for i, line in enumerate(lines):
            if "mkdir -p /etc/alisa" in line:
                mkdir_line_idx = i
            if "tee /etc/alisa/environment" in line:
                tee_line_idx = i
        
        assert mkdir_line_idx is not None, "mkdir -p /etc/alisa not found in install.sh"
        assert tee_line_idx is not None, "tee /etc/alisa/environment not found in install.sh"
        assert mkdir_line_idx < tee_line_idx, f"mkdir (line {mkdir_line_idx}) should come before tee (line {tee_line_idx})"
    
    def test_install_sh_supports_lang_switch(self):
        """Test that install.sh supports LANG environment variable."""
        install_script = Path(__file__).parent.parent / "setup" / "install.sh"
        with open(install_script) as f:
            content = f.read()
        
        # Check for LANG variable definition
        assert "LANG=${LANG:-uz}" in content, "install.sh should define LANG variable with default 'uz'"
        
        # Check for uz branch
        assert 'if [ "$LANG" = "uz" ]' in content, "install.sh should have conditional branch for LANG=uz"
        
        # Check for different model downloads based on language
        assert "base.en" in content, "install.sh should download base.en model for English"
        assert "base" in content, "install.sh should download base model for multilingual"
