"""
Risk and volatility analysis package.

This package contains modules for analyzing market data:
- risk_analyzer: Portfolio risk and scenario analysis
- volatility: Volatility calculation (realized, implied, blended)
- volatility_models: Volatility data models and structures
- volatility_integration: Integration helpers for volatility with options chains

All classes and functions are re-exported at the package level for convenience.
"""

# Import from risk_analyzer
from src.analysis.risk_analyzer import (
    CombinedAnalysis,
    IncomeMetrics,
    RiskAnalyzer,
    RiskMetrics,
    ScenarioOutcome,
    ScenarioResult,
)

# Import from volatility
from src.analysis.volatility import (
    BlendWeights,
    VolatilityCalculator,
    VolatilityConfig,
)

# Import from volatility_models
from src.analysis.volatility_models import PriceData, VolatilityResult

# Import from volatility_integration
from src.analysis.volatility_integration import (
    calculate_iv_term_structure,
    calculate_volatility_with_iv,
    extract_atm_implied_volatility,
    get_nearest_weekly_expiration,
    validate_price_data_quality,
)

__all__ = [
    # risk_analyzer
    "CombinedAnalysis",
    "IncomeMetrics",
    "RiskAnalyzer",
    "RiskMetrics",
    "ScenarioOutcome",
    "ScenarioResult",
    # volatility
    "BlendWeights",
    "VolatilityCalculator",
    "VolatilityConfig",
    # volatility_models
    "PriceData",
    "VolatilityResult",
    # volatility_integration
    "calculate_iv_term_structure",
    "calculate_volatility_with_iv",
    "extract_atm_implied_volatility",
    "get_nearest_weekly_expiration",
    "validate_price_data_quality",
]
