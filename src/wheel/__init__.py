"""
Wheel Strategy Tool - Manage options wheel strategy positions.

This package provides tools for tracking and executing the wheel strategy
across multiple symbols, with a bias toward premium collection.

Public API:
    WheelManager: Main orchestrator for wheel operations
    WheelPosition: Current state of a wheel position
    TradeRecord: Record of a single option trade
    WheelRecommendation: Recommendation for next trade
    WheelPerformance: Performance metrics
    WheelState: State machine states
    TradeOutcome: Possible trade outcomes
"""

from .exceptions import (
    DataFetchError,
    DuplicateSymbolError,
    InsufficientCapitalError,
    InvalidStateError,
    SymbolNotFoundError,
    TradeNotFoundError,
    WheelError,
)
from .models import (
    TradeRecord,
    WheelPerformance,
    WheelPosition,
    WheelRecommendation,
)
from .state import (
    VALID_TRANSITIONS,
    TradeOutcome,
    WheelState,
    can_transition,
    get_next_state,
    get_valid_actions,
)

__all__ = [
    # Core classes
    "WheelPosition",
    "TradeRecord",
    "WheelRecommendation",
    "WheelPerformance",
    # State machine
    "WheelState",
    "TradeOutcome",
    "VALID_TRANSITIONS",
    "can_transition",
    "get_next_state",
    "get_valid_actions",
    # Exceptions
    "WheelError",
    "InvalidStateError",
    "SymbolNotFoundError",
    "TradeNotFoundError",
    "DuplicateSymbolError",
    "InsufficientCapitalError",
    "DataFetchError",
]

# Deferred imports to avoid circular dependencies
def __getattr__(name: str):
    """Lazy import for WheelManager to avoid circular imports."""
    if name == "WheelManager":
        from .manager import WheelManager
        return WheelManager
    if name == "RecommendEngine":
        from .recommend import RecommendEngine
        return RecommendEngine
    if name == "PerformanceTracker":
        from .performance import PerformanceTracker
        return PerformanceTracker
    if name == "WheelRepository":
        from .repository import WheelRepository
        return WheelRepository
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
