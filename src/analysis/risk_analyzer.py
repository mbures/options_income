"""
Risk analysis module for covered options strategies.

This module provides comprehensive risk metrics, income analysis, and scenario
modeling for covered calls and cash-secured puts.

DEPRECATED: This module is maintained for backward compatibility only.
New code should import from:
- src.analysis.risk_models for data classes
- src.analysis.risk_calculator for calculation methods
- src.analysis.risk_reporter for analysis orchestration

Key features:
- Income metrics (annualized yield, return if flat/called)
- Risk metrics (expected value, opportunity cost, risk-adjusted return)
- Scenario analysis at various price levels
- Comparison to buy-and-hold strategies

Example:
    from src.analysis.risk_analyzer import RiskAnalyzer

    analyzer = RiskAnalyzer()

    # Analyze a covered call position
    metrics = analyzer.calculate_covered_call_metrics(
        current_price=100.0,
        strike=105.0,
        premium=2.50,
        days_to_expiry=30,
        probability_itm=0.25
    )

    # Run scenario analysis
    scenarios = analyzer.calculate_scenarios(
        current_price=100.0,
        strike=105.0,
        premium=2.50,
        option_type="call"
    )
"""

# Re-export all data models for backward compatibility
from .risk_models import (
    IncomeMetrics,
    RiskMetrics,
    ScenarioOutcome,
    ScenarioResult,
    CombinedAnalysis,
)

# Re-export calculator and reporter classes
from .risk_calculator import RiskCalculator
from .risk_reporter import RiskReporter


class RiskAnalyzer:
    """
    Legacy risk analyzer class - maintained for backward compatibility.

    This class wraps both RiskCalculator and RiskReporter to provide
    the same interface as before the refactoring.

    New code should use RiskReporter directly, which provides the same
    analyze_* methods.
    """

    def __init__(self, risk_free_rate: float = 0.05):
        """
        Initialize the risk analyzer.

        Args:
            risk_free_rate: Risk-free rate for calculations (default 5%)
        """
        self.calculator = RiskCalculator(risk_free_rate=risk_free_rate)
        self.reporter = RiskReporter(risk_free_rate=risk_free_rate)
        self.risk_free_rate = risk_free_rate

    # Delegate calculation methods to calculator
    def calculate_income_metrics(self, *args, **kwargs):
        """Calculate income metrics. See RiskCalculator.calculate_income_metrics."""
        return self.calculator.calculate_income_metrics(*args, **kwargs)

    def calculate_risk_metrics(self, *args, **kwargs):
        """Calculate risk metrics. See RiskCalculator.calculate_risk_metrics."""
        return self.calculator.calculate_risk_metrics(*args, **kwargs)

    def calculate_scenarios(self, *args, **kwargs):
        """Calculate scenarios. See RiskCalculator.calculate_scenarios."""
        return self.calculator.calculate_scenarios(*args, **kwargs)

    # Delegate reporting methods to reporter
    def analyze_covered_call(self, *args, **kwargs):
        """Analyze covered call. See RiskReporter.analyze_covered_call."""
        return self.reporter.analyze_covered_call(*args, **kwargs)

    def analyze_cash_secured_put(self, *args, **kwargs):
        """Analyze cash-secured put. See RiskReporter.analyze_cash_secured_put."""
        return self.reporter.analyze_cash_secured_put(*args, **kwargs)

    def compare_strategies(self, *args, **kwargs):
        """Compare strategies. See RiskReporter.compare_strategies."""
        return self.reporter.compare_strategies(*args, **kwargs)


# Export everything for backward compatibility
__all__ = [
    "RiskAnalyzer",
    "RiskCalculator",
    "RiskReporter",
    "IncomeMetrics",
    "RiskMetrics",
    "ScenarioOutcome",
    "ScenarioResult",
    "CombinedAnalysis",
]
