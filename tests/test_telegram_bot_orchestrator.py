"""Test telegram bot orchestrator module integration."""

import importlib.util
import pytest


def test_orchestrate_module_exists():
    """Test that ai_orchestrator.__main__ module exists and can be imported."""
    # Test that the module can be found
    spec = importlib.util.find_spec('ai_orchestrator.__main__')
    assert spec is not None, "ai_orchestrator.__main__ module not found"
    
    # Test that the module can be imported
    module = importlib.import_module('ai_orchestrator.__main__')
    assert module is not None
    
    # Test that it has the expected structure
    assert hasattr(module, '__name__')
    assert module.__name__ == 'ai_orchestrator.__main__'


def test_orchestrator_main_function_exists():
    """Test that orchestrator.main function exists."""
    from ai_orchestrator.orchestrator import main
    assert callable(main), "orchestrator.main should be callable"
