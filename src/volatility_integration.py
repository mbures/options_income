"""
DEPRECATED: This module has moved to src.analysis.volatility_integration

This compatibility module provides backward-compatible imports.
Please update your imports to use:
    from src.analysis.volatility_integration import ...

This compatibility layer will be removed in a future version.
"""

import warnings

# Issue deprecation warning when this module is imported
warnings.warn(
    "Importing from 'src.volatility_integration' is deprecated. "
    "Please use 'from src.analysis.volatility_integration import ...' instead. "
    "This compatibility layer will be removed in a future version.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export all public APIs from the new location
from src.analysis.volatility_integration import (
    calculate_iv_term_structure,
    calculate_volatility_with_iv,
    extract_atm_implied_volatility,
    get_nearest_weekly_expiration,
    validate_price_data_quality,
)

__all__ = [
    "calculate_iv_term_structure",
    "calculate_volatility_with_iv",
    "extract_atm_implied_volatility",
    "get_nearest_weekly_expiration",
    "validate_price_data_quality",
]
