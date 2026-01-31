"""
DEPRECATED: This module has moved to src.strategies.strike_optimizer

This compatibility module provides backward-compatible imports.
Please update your imports to use:
    from src.strategies.strike_optimizer import ...

This compatibility layer will be removed in a future version.
"""

import warnings

# Issue deprecation warning when this module is imported
warnings.warn(
    "Importing from 'src.strike_optimizer' is deprecated. "
    "Please use 'from src.strategies.strike_optimizer import ...' instead. "
    "This compatibility layer will be removed in a future version.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export all public APIs from the new location
from src.strategies.strike_optimizer import StrikeOptimizer

# Re-export models (from src.models)
from src.models import (
    PROFILE_SIGMA_RANGES,
    ProbabilityResult,
    StrikeProfile,
    StrikeRecommendation,
    StrikeResult,
)

__all__ = [
    "StrikeOptimizer",
    "PROFILE_SIGMA_RANGES",
    "ProbabilityResult",
    "StrikeProfile",
    "StrikeRecommendation",
    "StrikeResult",
]
