"""
Risk reporting and analysis orchestration module.

This module provides high-level analysis methods that orchestrate
risk calculations and produce combined analysis results.
"""

import logging
from typing import Any, Optional

from .risk_models import CombinedAnalysis
from .risk_calculator import RiskCalculator

logger = logging.getLogger(__name__)


class RiskReporter:
    """Reporter for generating combined risk analysis results."""

    def __init__(self, risk_free_rate: float = 0.05):
        """
        Initialize the risk reporter.

        Args:
            risk_free_rate: Risk-free rate for calculations (default 5%)
        """
        self.calculator = RiskCalculator(risk_free_rate=risk_free_rate)
        logger.info(f"RiskReporter initialized with risk_free_rate={risk_free_rate}")

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

        income = self.calculator.calculate_income_metrics(
            current_price=current_price,
            strike=strike,
            premium=premium,
            days_to_expiry=days_to_expiry,
            option_type="call",
            shares=shares,
            cost_basis=cost_basis,
        )

        risk = self.calculator.calculate_risk_metrics(
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
            scenarios = self.calculator.calculate_scenarios(
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

        income = self.calculator.calculate_income_metrics(
            current_price=current_price,
            strike=strike,
            premium=premium,
            days_to_expiry=days_to_expiry,
            option_type="put",
            shares=shares,
        )

        risk = self.calculator.calculate_risk_metrics(
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
            scenarios = self.calculator.calculate_scenarios(
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
