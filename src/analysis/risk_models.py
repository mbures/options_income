"""
Risk analysis data models.

This module defines the data classes used by the risk analysis system,
including income metrics, risk metrics, scenario outcomes, and combined analysis results.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class IncomeMetrics:
    """
    Income metrics for a covered option position.

    Attributes:
        premium_per_share: Premium received per share
        total_premium: Total premium for the position
        annualized_yield_pct: Annualized yield as percentage
        return_if_flat_pct: Return if stock unchanged (as percentage)
        return_if_called_pct: Return if called/assigned (as percentage)
        breakeven: Stock price at breakeven
        days_to_expiry: Days until expiration
        max_profit: Maximum possible profit
        max_loss: Maximum possible loss
    """

    premium_per_share: float
    total_premium: float
    annualized_yield_pct: float
    return_if_flat_pct: float
    return_if_called_pct: float
    breakeven: float
    days_to_expiry: int
    max_profit: float
    max_loss: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "premium_per_share": round(self.premium_per_share, 4),
            "total_premium": round(self.total_premium, 2),
            "annualized_yield_pct": round(self.annualized_yield_pct, 2),
            "return_if_flat_pct": round(self.return_if_flat_pct, 2),
            "return_if_called_pct": round(self.return_if_called_pct, 2),
            "breakeven": round(self.breakeven, 4),
            "days_to_expiry": self.days_to_expiry,
            "max_profit": round(self.max_profit, 2),
            "max_loss": round(self.max_loss, 2),
        }


@dataclass
class RiskMetrics:
    """
    Risk metrics for a covered option position.

    Attributes:
        probability_profit: Probability of profitable outcome
        probability_max_profit: Probability of achieving max profit
        expected_value: Expected value of the position
        expected_return_pct: Expected return as percentage
        opportunity_cost: Estimated opportunity cost if called
        opportunity_cost_pct: Opportunity cost as percentage
        downside_protection_pct: Downside protection from premium
        risk_reward_ratio: Ratio of max profit to max loss
        sharpe_like_ratio: Risk-adjusted return ratio
    """

    probability_profit: float
    probability_max_profit: float
    expected_value: float
    expected_return_pct: float
    opportunity_cost: float
    opportunity_cost_pct: float
    downside_protection_pct: float
    risk_reward_ratio: float
    sharpe_like_ratio: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "probability_profit_pct": round(self.probability_profit * 100, 2),
            "probability_max_profit_pct": round(self.probability_max_profit * 100, 2),
            "expected_value": round(self.expected_value, 2),
            "expected_return_pct": round(self.expected_return_pct, 2),
            "opportunity_cost": round(self.opportunity_cost, 2),
            "opportunity_cost_pct": round(self.opportunity_cost_pct, 2),
            "downside_protection_pct": round(self.downside_protection_pct, 2),
            "risk_reward_ratio": round(self.risk_reward_ratio, 4),
            "sharpe_like_ratio": round(self.sharpe_like_ratio, 2),
        }


@dataclass
class ScenarioOutcome:
    """
    Outcome at a specific price scenario.

    Attributes:
        price_level: Stock price at this scenario
        price_change_pct: Percentage change from current price
        stock_pnl: P&L from stock position only
        option_pnl: P&L from option position only
        total_pnl: Combined P&L
        total_return_pct: Total return as percentage
        buy_hold_pnl: P&L if just held stock (no option)
        buy_hold_return_pct: Buy-and-hold return as percentage
        strategy_vs_hold: Difference between strategy and buy-hold
    """

    price_level: float
    price_change_pct: float
    stock_pnl: float
    option_pnl: float
    total_pnl: float
    total_return_pct: float
    buy_hold_pnl: float
    buy_hold_return_pct: float
    strategy_vs_hold: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "price_level": round(self.price_level, 2),
            "price_change_pct": round(self.price_change_pct, 2),
            "stock_pnl": round(self.stock_pnl, 2),
            "option_pnl": round(self.option_pnl, 2),
            "total_pnl": round(self.total_pnl, 2),
            "total_return_pct": round(self.total_return_pct, 2),
            "buy_hold_pnl": round(self.buy_hold_pnl, 2),
            "buy_hold_return_pct": round(self.buy_hold_return_pct, 2),
            "strategy_vs_hold": round(self.strategy_vs_hold, 2),
        }


@dataclass
class ScenarioResult:
    """
    Complete scenario analysis result.

    Attributes:
        current_price: Current stock price
        strike: Option strike price
        premium: Premium received
        option_type: "call" or "put"
        shares: Number of shares
        scenarios: List of scenario outcomes
        best_scenario: Scenario with highest total return
        worst_scenario: Scenario with lowest total return
        breakeven_price: Price at which P&L is zero
    """

    current_price: float
    strike: float
    premium: float
    option_type: str
    shares: int
    scenarios: list[ScenarioOutcome]
    best_scenario: ScenarioOutcome
    worst_scenario: ScenarioOutcome
    breakeven_price: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "current_price": round(self.current_price, 2),
            "strike": round(self.strike, 2),
            "premium": round(self.premium, 4),
            "option_type": self.option_type,
            "shares": self.shares,
            "scenarios": [s.to_dict() for s in self.scenarios],
            "best_scenario": self.best_scenario.to_dict(),
            "worst_scenario": self.worst_scenario.to_dict(),
            "breakeven_price": round(self.breakeven_price, 2),
        }


@dataclass
class CombinedAnalysis:
    """
    Combined analysis results for an options position.

    Attributes:
        income_metrics: Income and return metrics
        risk_metrics: Risk and probability metrics
        scenario_analysis: Scenario analysis results
        warnings: List of warning messages
    """

    income_metrics: IncomeMetrics
    risk_metrics: RiskMetrics
    scenario_analysis: Optional[ScenarioResult] = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "income_metrics": self.income_metrics.to_dict(),
            "risk_metrics": self.risk_metrics.to_dict(),
            "warnings": self.warnings,
        }
        if self.scenario_analysis:
            result["scenario_analysis"] = self.scenario_analysis.to_dict()
        return result
