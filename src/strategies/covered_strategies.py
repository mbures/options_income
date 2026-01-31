"""
Covered options strategies module.

This module provides analyzers for covered call, covered put (cash-secured put),
and wheel strategy implementations.

DEPRECATED: This module is maintained for backward compatibility only.
New code should import from:
- src.strategies.covered_call for CoveredCallAnalyzer
- src.strategies.covered_put for CoveredPutAnalyzer
- src.strategies.wheel_strategy for WheelStrategy

Each strategy has been split into its own module for better organization
and maintainability.

Example:
    from src.strategies.covered_strategies import CoveredCallAnalyzer

    analyzer = CoveredCallAnalyzer()
    result = analyzer.analyze(symbol="AAPL", strike=150.0, ...)
"""

# Re-export all classes for backward compatibility
from .covered_call import CoveredCallAnalyzer
from .covered_put import CoveredPutAnalyzer
from .wheel_strategy import WheelStrategy

__all__ = [
    "CoveredCallAnalyzer",
    "CoveredPutAnalyzer",
    "WheelStrategy",
]
