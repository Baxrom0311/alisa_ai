"""LLM interface with multi-provider fallback chain.

DEPRECATED: This module is deprecated. Use alisa.brain.llm_manager.LLMManager directly.
"""

import warnings
from alisa.brain.llm_manager import generate_with_fallback

# Issue deprecation warning on import
warnings.warn(
    "alisa.brain.llm is deprecated. Use alisa.brain.llm_manager.LLMManager directly.",
    DeprecationWarning,
    stacklevel=2
)

# Re-export for backward compatibility
__all__ = ['generate_with_fallback']
