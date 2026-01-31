"""
Options trading strategies package.

This package contains modules for analyzing and building options strategies:
- covered_strategies: Covered calls, cash-secured puts, wheel strategy
- strike_optimizer: Strike price optimization and probability calculations
- ladder_builder: Multi-week position laddering

All classes and functions are re-exported at the package level for convenience.
"""

# Import from covered_strategies
from src.strategies.covered_strategies import (
    CoveredCallAnalyzer,
    CoveredPutAnalyzer,
    WheelStrategy,
)

# Import from strike_optimizer
from src.strategies.strike_optimizer import StrikeOptimizer

# Import from ladder_builder
from src.strategies.ladder_builder import LadderBuilder

__all__ = [
    # covered_strategies
    "CoveredCallAnalyzer",
    "CoveredPutAnalyzer",
    "WheelStrategy",
    # strike_optimizer
    "StrikeOptimizer",
    # ladder_builder
    "LadderBuilder",
]
