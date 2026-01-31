"""
Risk calculation module.

This module provides calculation methods for income metrics, risk metrics,
and scenario analysis for covered options strategies.
"""

import logging
from typing import Optional

from .risk_models import (
    IncomeMetrics,
    RiskMetrics,
    ScenarioOutcome,
    ScenarioResult,
)

logger = logging.getLogger(__name__)


class RiskCalculator:
    """Calculator for risk and income metrics of options positions."""

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
