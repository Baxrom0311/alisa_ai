"""Warning filters for Alisa AI Assistant."""

import warnings
import structlog

logger = structlog.get_logger()


def setup_warning_filters():
    """Setup warning filters to suppress known deprecation warnings."""
    
    # Suppress aiohttp asyncio.iscoroutinefunction deprecation warnings
    # These are from the aiohttp library and will be fixed in future versions
    warnings.filterwarnings(
        "ignore",
        message="'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction\\(\\) instead",
        category=DeprecationWarning
    )
    
    # More general filter for aiohttp deprecation warnings
    warnings.filterwarnings(
        "ignore",
        message="'asyncio.iscoroutinefunction' is deprecated.*",
        category=DeprecationWarning
    )
    
    logger.debug("warning_filters_configured", 
                filters=["aiohttp asyncio.iscoroutinefunction deprecation"])


def suppress_warnings_context():
    """Context manager to temporarily suppress all warnings."""
    return warnings.catch_warnings()


# Auto-configure warnings when module is imported
setup_warning_filters()
