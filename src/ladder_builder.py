"""
DEPRECATED: This module has moved to src.strategies.ladder_builder

This compatibility module provides backward-compatible imports.
Please update your imports to use:
    from src.strategies.ladder_builder import ...

This compatibility layer will be removed in a future version.
"""

import warnings

# Issue deprecation warning when this module is imported
warnings.warn(
    "Importing from 'src.ladder_builder' is deprecated. "
    "Please use 'from src.strategies.ladder_builder import ...' instead. "
    "This compatibility layer will be removed in a future version.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export all public APIs from the new location
from src.strategies.ladder_builder import LadderBuilder

# Re-export models (from src.models.ladder)
from src.models.ladder import (
    ALLOCATION_WEIGHTS,
    AllocationStrategy,
    LadderConfig,
    LadderLeg,
    LadderResult,
    WeeklyExpirationDay,
)

__all__ = [
    "LadderBuilder",
    "ALLOCATION_WEIGHTS",
    "AllocationStrategy",
    "LadderConfig",
    "LadderLeg",
    "LadderResult",
    "WeeklyExpirationDay",
]
