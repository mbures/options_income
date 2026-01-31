"""
DEPRECATED: This module has moved to src.strategies.covered_strategies

This compatibility module provides backward-compatible imports.
Please update your imports to use:
    from src.strategies.covered_strategies import ...

This compatibility layer will be removed in a future version.
"""

import warnings

# Issue deprecation warning when this module is imported
warnings.warn(
    "Importing from 'src.covered_strategies' is deprecated. "
    "Please use 'from src.strategies.covered_strategies import ...' instead. "
    "This compatibility layer will be removed in a future version.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export all public APIs from the new location
from src.strategies.covered_strategies import (
    CoveredCallAnalyzer,
    CoveredPutAnalyzer,
    WheelStrategy,
)

# Re-export constants (still at src level)
from src.constants import MAX_BID_ASK_SPREAD_PCT, MIN_BID_PRICE, MIN_OPEN_INTEREST

# Re-export models (still at src level)
from src.models import (
    CoveredCallResult,
    CoveredPutResult,
    WheelCycleMetrics,
    WheelRecommendation,
    WheelState,
)

__all__ = [
    # Constants
    "MAX_BID_ASK_SPREAD_PCT",
    "MIN_BID_PRICE",
    "MIN_OPEN_INTEREST",
    # Analyzers
    "CoveredCallAnalyzer",
    "CoveredPutAnalyzer",
    "WheelStrategy",
    # Models
    "CoveredCallResult",
    "CoveredPutResult",
    "WheelCycleMetrics",
    "WheelRecommendation",
    "WheelState",
]
