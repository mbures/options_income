"""
DEPRECATED: This module has moved to src.market_data.earnings_calendar

This compatibility module provides backward-compatible imports.
Please update your imports to use:
    from src.market_data.earnings_calendar import ...

This compatibility layer will be removed in a future version.
"""

import warnings

# Issue deprecation warning when this module is imported
warnings.warn(
    "Importing from 'src.earnings_calendar' is deprecated. "
    "Please use 'from src.market_data.earnings_calendar import ...' instead. "
    "This compatibility layer will be removed in a future version.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export all public APIs from the new location
from src.market_data.earnings_calendar import EarningsCalendar, EarningsEvent

__all__ = [
    "EarningsCalendar",
    "EarningsEvent",
]
