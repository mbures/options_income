"""
DEPRECATED: This module has moved to src.analysis.volatility_models

This compatibility module provides backward-compatible imports.
Please update your imports to use:
    from src.analysis.volatility_models import ...

This compatibility layer will be removed in a future version.
"""

import warnings

# Issue deprecation warning when this module is imported
warnings.warn(
    "Importing from 'src.volatility_models' is deprecated. "
    "Please use 'from src.analysis.volatility_models import ...' instead. "
    "This compatibility layer will be removed in a future version.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export all public APIs from the new location
from src.analysis.volatility_models import PriceData, VolatilityResult

__all__ = [
    "PriceData",
    "VolatilityResult",
]
