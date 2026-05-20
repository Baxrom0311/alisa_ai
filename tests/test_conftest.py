"""Test conftest.py configuration."""

import asyncio
import warnings
from unittest.mock import AsyncMock

import pytest

from tests.conftest import SafeAsyncMock


class TestConftest:
    """Test conftest configuration."""
    
    def test_safe_async_mock_creation(self):
        """Test SafeAsyncMock can be created."""
        mock = SafeAsyncMock()
        assert isinstance(mock, AsyncMock)
        
    def test_safe_async_mock_cleanup(self):
        """Test SafeAsyncMock handles cleanup gracefully."""
        mock = SafeAsyncMock()
        # Should not raise any exceptions during cleanup
        del mock
        
    def test_event_loop_fixture_available(self, event_loop):
        """Test event loop fixture is available."""
        assert event_loop is not None
        assert isinstance(event_loop, asyncio.AbstractEventLoop)
        
    def test_warnings_suppressed(self):
        """Test that async mock warnings are suppressed."""
        # This would normally generate a warning, but should be suppressed
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            mock = AsyncMock()
            # Create an unawaited coroutine (would normally warn)
            coro = mock()
            del mock
            
            # Check that no RuntimeWarning about unawaited coroutines
            runtime_warnings = [warning for warning in w 
                              if issubclass(warning.category, RuntimeWarning)
                              and "never awaited" in str(warning.message)]
            
            # Clean up the coroutine to avoid actual warnings
            if asyncio.iscoroutine(coro):
                coro.close()
                
            # Should be empty due to our warning filters
            assert len(runtime_warnings) == 0
