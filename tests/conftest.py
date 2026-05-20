"""Test configuration and fixtures."""

import asyncio
import warnings
from unittest.mock import AsyncMock

import pytest


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    try:
        loop = asyncio.new_event_loop()
    except Exception:
        # Fallback for older Python versions
        loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


def pytest_configure(config):
    """Configure pytest to suppress known warnings."""
    warnings.filterwarnings(
        "ignore",
        message="coroutine 'AsyncMockMixin._execute_mock_call' was never awaited",
        category=RuntimeWarning
    )
    warnings.filterwarnings(
        "ignore", 
        message="Enable tracemalloc to get the object allocation traceback",
        category=RuntimeWarning
    )
    # Suppress aiohttp asyncio.iscoroutinefunction deprecation warnings
    warnings.filterwarnings(
        "ignore",
        message="'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction\\(\\) instead",
        category=DeprecationWarning
    )
    warnings.filterwarnings(
        "ignore",
        message="'asyncio.iscoroutinefunction' is deprecated.*",
        category=DeprecationWarning
    )


class SafeAsyncMock(AsyncMock):
    """AsyncMock that properly handles cleanup to avoid warnings."""
    
    def __del__(self):
        """Clean up any pending coroutines."""
        try:
            # Close any pending coroutines
            if hasattr(self, '_mock_calls'):
                for call in self._mock_calls:
                    if asyncio.iscoroutine(call):
                        call.close()
        except Exception:
            pass  # Ignore cleanup errors
