"""
DEPRECATED: This module has moved to src.analysis.risk_analyzer

This compatibility module provides backward-compatible imports.
Please update your imports to use:
    from src.analysis.risk_analyzer import ...

This compatibility layer will be removed in a future version.
"""

import warnings

# Issue deprecation warning when this module is imported
warnings.warn(
    "Importing from 'src.risk_analyzer' is deprecated. "
    "Please use 'from src.analysis.risk_analyzer import ...' instead. "
    "This compatibility layer will be removed in a future version.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export all public APIs from the new location
from src.analysis.risk_analyzer import (
    CombinedAnalysis,
    IncomeMetrics,
    RiskAnalyzer,
    RiskMetrics,
    ScenarioOutcome,
    ScenarioResult,
)

__all__ = [
    "CombinedAnalysis",
    "IncomeMetrics",
    "RiskAnalyzer",
    "RiskMetrics",
    "ScenarioOutcome",
    "ScenarioResult",
]
