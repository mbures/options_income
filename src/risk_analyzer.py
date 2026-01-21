"""
Risk analysis module for covered options strategies.

This module provides comprehensive risk metrics, income analysis, and scenario
modeling for covered calls and cash-secured puts.

Key features:
- Income metrics (annualized yield, return if flat/called)
- Risk metrics (expected value, opportunity cost, risk-adjusted return)
- Scenario analysis at various price levels
- Comparison to buy-and-hold strategies

Example:
    from src.risk_analyzer import RiskAnalyzer

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

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


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
            "sharpe_like_ratio": round(self.sharpe_like_ratio, 4),
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
    Combined income and risk analysis for a position.

    Attributes:
        income_metrics: Income-related metrics
        risk_metrics: Risk-related metrics
        scenario_analysis: Scenario outcomes (if calculated)
        warnings: List of warnings
    """

    income_metrics: IncomeMetrics
    risk_metrics: RiskMetrics
    scenario_analysis: Optional[ScenarioResult] = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "income_metrics": self.income_metrics.to_dict(),
            "risk_metrics": self.risk_metrics.to_dict(),
            "scenario_analysis": self.scenario_analysis.to_dict()
            if self.scenario_analysis
            else None,
            "warnings": self.warnings,
        }


class RiskAnalyzer:
    """
    Analyzer for risk and income metrics of covered options positions.

    Provides comprehensive analysis including:
    - Income metrics (yields, returns, breakevens)
    - Risk metrics (expected value, opportunity cost, risk-adjusted returns)
    - Scenario analysis at various price levels

    Example:
        analyzer = RiskAnalyzer()

        # Full analysis for a covered call
        analysis = analyzer.analyze_covered_call(
            current_price=100.0,
            strike=105.0,
            premium=2.50,
            days_to_expiry=30,
            probability_itm=0.25,
            shares=100,
            price_target=110.0
        )

        print(f"Expected value: ${analysis.risk_metrics.expected_value:.2f}")
        print(f"Annualized yield: {analysis.income_metrics.annualized_yield_pct:.2f}%")
    """

    def __init__(self, risk_free_rate: float = 0.05):
        """
        Initialize the risk analyzer.

        Args:
            risk_free_rate: Risk-free rate for calculations (default 5%)
        """
        self.risk_free_rate = risk_free_rate
        logger.info(f"RiskAnalyzer initialized with risk_free_rate={risk_free_rate}")

    def calculate_income_metrics(
        self,
        current_price: float,
        strike: float,
        premium: float,
        days_to_expiry: int,
        option_type: str = "call",
        shares: int = 100,
        cost_basis: Optional[float] = None,
    ) -> IncomeMetrics:
        """
        Calculate income metrics for a covered option position.

        Args:
            current_price: Current stock price
            strike: Option strike price
            premium: Premium per share received
            days_to_expiry: Days until expiration
            option_type: "call" or "put"
            shares: Number of shares (default 100)
            cost_basis: Cost basis per share (default: current_price)

        Returns:
            IncomeMetrics with all calculated values
        """
        if cost_basis is None:
            cost_basis = current_price

        total_premium = premium * shares
        position_value = current_price * shares

        # Calculate annualized yield
        if days_to_expiry > 0 and position_value > 0:
            annualized_yield = (total_premium / position_value) * (365 / days_to_expiry) * 100
        else:
            annualized_yield = 0.0

        # Return if flat (stock unchanged)
        return_if_flat = (total_premium / position_value) * 100 if position_value > 0 else 0.0

        if option_type.lower() == "call":
            # Covered call metrics
            breakeven = current_price - premium
            appreciation = (strike - cost_basis) * shares
            max_profit = total_premium + appreciation
            return_if_called = (max_profit / position_value) * 100 if position_value > 0 else 0.0
            # Max loss: stock goes to zero minus premium received
            max_loss = position_value - total_premium
        else:
            # Cash-secured put metrics
            collateral = strike * shares
            breakeven = strike - premium
            max_profit = total_premium
            return_if_called = (
                (-(strike - current_price) * shares + total_premium) / collateral * 100
                if collateral > 0
                else 0.0
            )
            # Max loss: stock goes to zero, assigned at strike minus premium
            max_loss = collateral - total_premium

        return IncomeMetrics(
            premium_per_share=premium,
            total_premium=total_premium,
            annualized_yield_pct=annualized_yield,
            return_if_flat_pct=return_if_flat,
            return_if_called_pct=return_if_called,
            breakeven=breakeven,
            days_to_expiry=days_to_expiry,
            max_profit=max_profit,
            max_loss=max_loss,
        )

    def calculate_risk_metrics(
        self,
        current_price: float,
        strike: float,
        premium: float,
        probability_itm: float,
        days_to_expiry: int,
        option_type: str = "call",
        shares: int = 100,
        price_target: Optional[float] = None,
        expected_volatility: float = 0.20,
    ) -> RiskMetrics:
        """
        Calculate risk metrics for a covered option position.

        Args:
            current_price: Current stock price
            strike: Option strike price
            premium: Premium per share received
            probability_itm: Probability of finishing ITM
            days_to_expiry: Days until expiration
            option_type: "call" or "put"
            shares: Number of shares (default 100)
            price_target: Expected price target (for opportunity cost)
            expected_volatility: Expected annualized volatility

        Returns:
            RiskMetrics with all calculated values
        """
        total_premium = premium * shares
        position_value = current_price * shares
        probability_otm = 1 - probability_itm

        if option_type.lower() == "call":
            # Covered call risk metrics
            # Probability of profit: premium received provides buffer
            # Profit if OTM (keep premium) or if called at profit
            prob_profit = probability_otm  # Always profitable if OTM due to premium

            # Max profit achieved when called at or above strike
            prob_max_profit = probability_itm

            # Expected value calculation
            # If OTM: keep shares + premium
            profit_if_otm = total_premium
            # If ITM: called away at strike, gain = (strike - current) * shares + premium
            profit_if_itm = (strike - current_price) * shares + total_premium

            expected_value = (probability_otm * profit_if_otm) + (probability_itm * profit_if_itm)

            # Opportunity cost: potential upside missed if stock rises above strike
            if price_target and price_target > strike:
                opportunity_cost = (price_target - strike) * shares * probability_itm
            else:
                # Estimate based on expected move
                expected_move = current_price * expected_volatility * (days_to_expiry / 365) ** 0.5
                potential_upside = max(0, current_price + expected_move - strike)
                opportunity_cost = potential_upside * shares * probability_itm

            # Downside protection: premium as percentage of stock price
            downside_protection = (premium / current_price) * 100

            # Max profit and max loss for ratio
            max_profit = total_premium + max(0, (strike - current_price) * shares)
            max_loss = position_value - total_premium  # Stock goes to zero

        else:
            # Cash-secured put risk metrics
            collateral = strike * shares

            # Profit if OTM (keep premium)
            prob_profit = probability_otm

            # Max profit is premium (when OTM)
            prob_max_profit = probability_otm

            # Expected value
            profit_if_otm = total_premium
            # If ITM: assigned, effective purchase at (strike - premium)
            # Loss relative to current price if assigned
            loss_if_itm = (strike - current_price) * shares - total_premium

            expected_value = (probability_otm * profit_if_otm) - (
                probability_itm * abs(loss_if_itm)
            )

            # Opportunity cost for puts: could have bought stock directly at lower price
            if price_target and price_target < current_price:
                opportunity_cost = (current_price - price_target) * shares * probability_otm
            else:
                opportunity_cost = 0.0

            # Downside protection: how much lower effective purchase is
            effective_purchase = strike - premium
            downside_protection = (
                ((current_price - effective_purchase) / current_price) * 100
                if probability_itm > 0
                else 0.0
            )

            max_profit = total_premium
            max_loss = collateral - total_premium

        # Calculate expected return percentage
        expected_return = (expected_value / position_value) * 100 if position_value > 0 else 0.0

        # Opportunity cost as percentage
        opp_cost_pct = (opportunity_cost / position_value) * 100 if position_value > 0 else 0.0

        # Risk-reward ratio
        risk_reward = max_profit / max_loss if max_loss > 0 else float("inf")

        # Sharpe-like ratio: (expected return - risk free) / volatility
        # Annualize the expected return
        if days_to_expiry > 0:
            annualized_return = expected_return * (365 / days_to_expiry)
            # Use expected volatility as proxy for standard deviation
            sharpe_like = (
                (annualized_return / 100 - self.risk_free_rate) / expected_volatility
                if expected_volatility > 0
                else 0.0
            )
        else:
            sharpe_like = 0.0

        return RiskMetrics(
            probability_profit=prob_profit,
            probability_max_profit=prob_max_profit,
            expected_value=expected_value,
            expected_return_pct=expected_return,
            opportunity_cost=opportunity_cost,
            opportunity_cost_pct=opp_cost_pct,
            downside_protection_pct=downside_protection,
            risk_reward_ratio=risk_reward,
            sharpe_like_ratio=sharpe_like,
        )

    def calculate_scenarios(
        self,
        current_price: float,
        strike: float,
        premium: float,
        option_type: str = "call",
        shares: int = 100,
        custom_levels: Optional[list[float]] = None,
    ) -> ScenarioResult:
        """
        Calculate outcomes at various price scenarios.

        Args:
            current_price: Current stock price
            strike: Option strike price
            premium: Premium per share received
            option_type: "call" or "put"
            shares: Number of shares (default 100)
            custom_levels: Custom price levels to analyze (optional)

        Returns:
            ScenarioResult with all scenario outcomes
        """
        total_premium = premium * shares
        position_value = current_price * shares

        # Default scenarios: -20%, -10%, -5%, ATM, Strike, +5%, +10%, +20%
        if custom_levels:
            price_levels = custom_levels
        else:
            price_levels = [
                current_price * 0.80,  # -20%
                current_price * 0.90,  # -10%
                current_price * 0.95,  # -5%
                current_price,  # ATM
                strike,  # At strike
                current_price * 1.05,  # +5%
                current_price * 1.10,  # +10%
                current_price * 1.20,  # +20%
            ]

        # Remove duplicates and sort
        price_levels = sorted(set(price_levels))

        scenarios = []
        for price in price_levels:
            price_change_pct = ((price - current_price) / current_price) * 100

            # Buy and hold P&L
            buy_hold_pnl = (price - current_price) * shares
            buy_hold_return = (buy_hold_pnl / position_value) * 100 if position_value > 0 else 0.0

            if option_type.lower() == "call":
                # Covered call scenarios
                # Stock P&L: gain capped at strike price if called away
                # If price >= strike: shares called away, receive (strike - current) per share
                # If price < strike: option expires, P&L = (price - current) per share
                effective_exit = min(price, strike)
                stock_pnl = (effective_exit - current_price) * shares

                # Option P&L: premium received (always kept since we sold the option)
                # The "assignment" obligation is handled by capping the stock gain at strike
                option_pnl = total_premium

                # If called away, total = (strike - current) * shares + premium
                # If not called, total = (price - current) * shares + premium
                total_pnl = stock_pnl + option_pnl

            else:
                # Cash-secured put scenarios
                if price >= strike:
                    # Put expires worthless
                    stock_pnl = 0  # No stock position
                    option_pnl = total_premium
                else:
                    # Put assigned - acquire shares at strike
                    # Effective purchase: strike - premium
                    # P&L: (price - strike + premium) * shares
                    stock_pnl = (price - strike) * shares
                    option_pnl = total_premium

                total_pnl = stock_pnl + option_pnl

                # Adjust buy_hold for puts: compare to if had bought stock at current
                buy_hold_pnl = (price - current_price) * shares
                buy_hold_return = (buy_hold_pnl / position_value) * 100 if position_value > 0 else 0

            total_return = (total_pnl / position_value) * 100 if position_value > 0 else 0.0
            strategy_vs_hold = total_pnl - buy_hold_pnl

            scenario = ScenarioOutcome(
                price_level=price,
                price_change_pct=price_change_pct,
                stock_pnl=stock_pnl,
                option_pnl=option_pnl,
                total_pnl=total_pnl,
                total_return_pct=total_return,
                buy_hold_pnl=buy_hold_pnl,
                buy_hold_return_pct=buy_hold_return,
                strategy_vs_hold=strategy_vs_hold,
            )
            scenarios.append(scenario)

        # Find best and worst scenarios
        best = max(scenarios, key=lambda s: s.total_return_pct)
        worst = min(scenarios, key=lambda s: s.total_return_pct)

        # Calculate breakeven price
        if option_type.lower() == "call":
            breakeven_price = current_price - premium
        else:
            breakeven_price = strike - premium

        return ScenarioResult(
            current_price=current_price,
            strike=strike,
            premium=premium,
            option_type=option_type,
            shares=shares,
            scenarios=scenarios,
            best_scenario=best,
            worst_scenario=worst,
            breakeven_price=breakeven_price,
        )

    def analyze_covered_call(
        self,
        current_price: float,
        strike: float,
        premium: float,
        days_to_expiry: int,
        probability_itm: float,
        shares: int = 100,
        cost_basis: Optional[float] = None,
        price_target: Optional[float] = None,
        expected_volatility: float = 0.20,
        include_scenarios: bool = True,
    ) -> CombinedAnalysis:
        """
        Perform complete analysis for a covered call position.

        Args:
            current_price: Current stock price
            strike: Call strike price
            premium: Premium per share received
            days_to_expiry: Days until expiration
            probability_itm: Probability of finishing ITM
            shares: Number of shares (default 100)
            cost_basis: Cost basis per share (default: current_price)
            price_target: Expected price target for opportunity cost
            expected_volatility: Expected annualized volatility
            include_scenarios: Whether to include scenario analysis

        Returns:
            CombinedAnalysis with all metrics
        """
        warnings = []

        # Validate inputs
        if strike <= current_price:
            warnings.append(f"ITM call: strike ({strike}) <= current ({current_price})")

        if premium <= 0:
            warnings.append("Zero or negative premium")

        income = self.calculate_income_metrics(
            current_price=current_price,
            strike=strike,
            premium=premium,
            days_to_expiry=days_to_expiry,
            option_type="call",
            shares=shares,
            cost_basis=cost_basis,
        )

        risk = self.calculate_risk_metrics(
            current_price=current_price,
            strike=strike,
            premium=premium,
            probability_itm=probability_itm,
            days_to_expiry=days_to_expiry,
            option_type="call",
            shares=shares,
            price_target=price_target,
            expected_volatility=expected_volatility,
        )

        scenarios = None
        if include_scenarios:
            scenarios = self.calculate_scenarios(
                current_price=current_price,
                strike=strike,
                premium=premium,
                option_type="call",
                shares=shares,
            )

        # Add contextual warnings
        if risk.opportunity_cost_pct > 5:
            warnings.append(
                f"High opportunity cost: {risk.opportunity_cost_pct:.1f}% potential upside capped"
            )

        if income.annualized_yield_pct < 5:
            warnings.append(f"Low annualized yield: {income.annualized_yield_pct:.1f}%")

        logger.info(
            f"Analyzed covered call: strike={strike}, premium={premium:.2f}, "
            f"EV=${risk.expected_value:.2f}, yield={income.annualized_yield_pct:.1f}%"
        )

        return CombinedAnalysis(
            income_metrics=income,
            risk_metrics=risk,
            scenario_analysis=scenarios,
            warnings=warnings,
        )

    def analyze_cash_secured_put(
        self,
        current_price: float,
        strike: float,
        premium: float,
        days_to_expiry: int,
        probability_itm: float,
        shares: int = 100,
        price_target: Optional[float] = None,
        expected_volatility: float = 0.20,
        include_scenarios: bool = True,
    ) -> CombinedAnalysis:
        """
        Perform complete analysis for a cash-secured put position.

        Args:
            current_price: Current stock price
            strike: Put strike price
            premium: Premium per share received
            days_to_expiry: Days until expiration
            probability_itm: Probability of finishing ITM
            shares: Number of shares equivalent (default 100)
            price_target: Target purchase price
            expected_volatility: Expected annualized volatility
            include_scenarios: Whether to include scenario analysis

        Returns:
            CombinedAnalysis with all metrics
        """
        warnings = []

        # Validate inputs
        if strike >= current_price:
            warnings.append(f"ITM put: strike ({strike}) >= current ({current_price})")

        if premium <= 0:
            warnings.append("Zero or negative premium")

        income = self.calculate_income_metrics(
            current_price=current_price,
            strike=strike,
            premium=premium,
            days_to_expiry=days_to_expiry,
            option_type="put",
            shares=shares,
        )

        risk = self.calculate_risk_metrics(
            current_price=current_price,
            strike=strike,
            premium=premium,
            probability_itm=probability_itm,
            days_to_expiry=days_to_expiry,
            option_type="put",
            shares=shares,
            price_target=price_target,
            expected_volatility=expected_volatility,
        )

        scenarios = None
        if include_scenarios:
            scenarios = self.calculate_scenarios(
                current_price=current_price,
                strike=strike,
                premium=premium,
                option_type="put",
                shares=shares,
            )

        # Add contextual warnings
        effective_purchase = strike - premium
        discount = ((current_price - effective_purchase) / current_price) * 100
        if discount < 3 and probability_itm > 0.20:
            warnings.append(
                f"Small discount ({discount:.1f}%) with high P(ITM) ({probability_itm * 100:.0f}%)"
            )

        if income.annualized_yield_pct < 5:
            warnings.append(f"Low annualized yield: {income.annualized_yield_pct:.1f}%")

        logger.info(
            f"Analyzed cash-secured put: strike={strike}, premium={premium:.2f}, "
            f"EV=${risk.expected_value:.2f}, yield={income.annualized_yield_pct:.1f}%"
        )

        return CombinedAnalysis(
            income_metrics=income,
            risk_metrics=risk,
            scenario_analysis=scenarios,
            warnings=warnings,
        )

    def compare_strategies(
        self,
        current_price: float,
        call_strike: float,
        call_premium: float,
        put_strike: float,
        put_premium: float,
        days_to_expiry: int,
        call_prob_itm: float,
        put_prob_itm: float,
        shares: int = 100,
    ) -> dict[str, Any]:
        """
        Compare covered call vs cash-secured put for same underlying.

        Args:
            current_price: Current stock price
            call_strike: Call strike price
            call_premium: Call premium per share
            put_strike: Put strike price
            put_premium: Put premium per share
            days_to_expiry: Days until expiration
            call_prob_itm: Probability call finishes ITM
            put_prob_itm: Probability put finishes ITM
            shares: Number of shares

        Returns:
            Dictionary comparing both strategies
        """
        call_analysis = self.analyze_covered_call(
            current_price=current_price,
            strike=call_strike,
            premium=call_premium,
            days_to_expiry=days_to_expiry,
            probability_itm=call_prob_itm,
            shares=shares,
            include_scenarios=False,
        )

        put_analysis = self.analyze_cash_secured_put(
            current_price=current_price,
            strike=put_strike,
            premium=put_premium,
            days_to_expiry=days_to_expiry,
            probability_itm=put_prob_itm,
            shares=shares,
            include_scenarios=False,
        )

        # Determine recommendation
        call_ev = call_analysis.risk_metrics.expected_value
        put_ev = put_analysis.risk_metrics.expected_value

        if call_ev > put_ev:
            recommendation = "covered_call"
            reason = f"Higher expected value (${call_ev:.2f} vs ${put_ev:.2f})"
        elif put_ev > call_ev:
            recommendation = "cash_secured_put"
            reason = f"Higher expected value (${put_ev:.2f} vs ${call_ev:.2f})"
        else:
            recommendation = "either"
            reason = "Similar expected values"

        return {
            "covered_call": call_analysis.to_dict(),
            "cash_secured_put": put_analysis.to_dict(),
            "recommendation": recommendation,
            "reason": reason,
            "ev_difference": call_ev - put_ev,
        }
