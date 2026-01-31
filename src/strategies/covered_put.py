"""
Covered options strategy analysis module.

This module provides tools for analyzing:
- Covered Calls: Selling calls against owned shares
- Cash-Secured Puts: Selling puts with cash collateral
- Wheel Strategy: Rotating between puts and calls

Each analyzer calculates:
- Premium income (based on bid prices)
- Assignment probability
- Various return scenarios (if flat, if assigned)
- Collateral requirements
- Risk warnings (liquidity, earnings, spreads)

Example:
    from src.covered_strategies import CoveredCallAnalyzer, CoveredPutAnalyzer

    # Analyze a covered call
    call_analyzer = CoveredCallAnalyzer(strike_optimizer)
    result = call_analyzer.analyze(
        contract=call_option,
        current_price=10.50,
        shares=100
    )
    print(f"Max profit if called: ${result.max_profit:.2f}")

    # Analyze a cash-secured put
    put_analyzer = CoveredPutAnalyzer(strike_optimizer)
    result = put_analyzer.analyze(
        contract=put_option,
        current_price=10.50
    )
    print(f"Effective buy price if assigned: ${result.effective_purchase_price:.2f}")
"""

import logging
from typing import Optional

from src.constants import MAX_BID_ASK_SPREAD_PCT, MIN_BID_PRICE, MIN_OPEN_INTEREST
from src.models import (
    CoveredCallResult,
    CoveredPutResult,
    OptionContract,
    OptionsChain,
    WheelCycleMetrics,
    WheelRecommendation,
    WheelState,
)
from src.strategies.strike_optimizer import StrikeOptimizer, StrikeProfile
from src.utils import calculate_days_to_expiry
from src.warnings import add_liquidity_warnings, check_early_assignment_risk, check_earnings_warning

logger = logging.getLogger(__name__)


# Re-export models for backward compatibility
__all__ = [
    "CoveredCallAnalyzer",
    "CoveredPutAnalyzer",
    "WheelStrategy",
    # Models (re-exported for convenience)
    "WheelState",
    "CoveredCallResult",
    "CoveredPutResult",
    "WheelRecommendation",
    "WheelCycleMetrics",
]



class CoveredPutAnalyzer:
    """
    Analyzer for cash-secured put strategies.

    A cash-secured put involves:
    - Setting aside cash equal to strike x 100 per contract
    - Selling an OTM put option
    - Collecting premium, potentially acquiring shares at discount

    Outcomes:
    - If stock > strike at expiry: Keep premium (profit = premium)
    - If stock <= strike at expiry: Buy shares at strike (effective cost = strike - premium)

    Example:
        analyzer = CoveredPutAnalyzer(strike_optimizer)
        result = analyzer.analyze(
            contract=put_option,
            current_price=10.50,
            volatility=0.30
        )
    """

    def __init__(self, strike_optimizer: StrikeOptimizer):
        """
        Initialize the covered put analyzer.

        Args:
            strike_optimizer: StrikeOptimizer for probability calculations
        """
        self.optimizer = strike_optimizer

    def analyze(
        self,
        contract: OptionContract,
        current_price: float,
        volatility: float,
        earnings_dates: Optional[list[str]] = None,
        ex_dividend_dates: Optional[list[str]] = None,
    ) -> CoveredPutResult:
        """
        Analyze a cash-secured put position.

        Args:
            contract: Put option contract to analyze
            current_price: Current stock price
            volatility: Annualized volatility for calculations
            earnings_dates: List of earnings dates to check (YYYY-MM-DD)
            ex_dividend_dates: List of ex-dividend dates to check (YYYY-MM-DD)

        Returns:
            CoveredPutResult with all metrics

        Raises:
            ValueError: If contract is not a put or is ITM
        """
        # Validate inputs
        if not contract.is_put:
            raise ValueError("Contract must be a put option")
        if contract.strike >= current_price:
            raise ValueError(
                f"Put strike ({contract.strike}) must be below current price ({current_price})"
            )

        warnings = []

        # Calculate days to expiry
        days_to_expiry = calculate_days_to_expiry(contract.expiration_date)

        # Get premium (bid price)
        premium_per_share = contract.bid if contract.bid else 0.0

        # Check for minimum premium
        if premium_per_share < MIN_BID_PRICE:
            warnings.append(f"Low premium: ${premium_per_share:.2f} (minimum ${MIN_BID_PRICE})")

        # Standard contract size
        shares_per_contract = 100
        total_premium = premium_per_share * shares_per_contract

        # Collateral required: strike x 100
        collateral_required = contract.strike * shares_per_contract

        # Effective purchase price if assigned
        effective_purchase_price = contract.strike - premium_per_share

        # Discount from current price
        discount_from_current = (current_price - effective_purchase_price) / current_price

        # Returns
        # Max profit (if OTM): premium
        max_profit = total_premium
        max_profit_pct = (max_profit / collateral_required) * 100 if collateral_required > 0 else 0

        # Max loss: if stock goes to zero, lose collateral minus premium
        max_loss = collateral_required - total_premium

        # Breakeven: strike - premium
        breakeven = contract.strike - premium_per_share

        # Profit if flat (stock unchanged): premium (put expires worthless)
        profit_if_flat = total_premium
        profit_if_flat_pct = (
            (profit_if_flat / collateral_required) * 100 if collateral_required > 0 else 0
        )

        # Annualized return if OTM
        if days_to_expiry > 0:
            annualized_if_otm = (max_profit / collateral_required) * (365 / days_to_expiry)
        else:
            annualized_if_otm = 0

        # Calculate assignment probability and sigma distance
        sigma_distance = None
        assignment_prob = None
        profile = None

        try:
            sigma_distance = self.optimizer.get_sigma_for_strike(
                strike=contract.strike,
                current_price=current_price,
                volatility=volatility,
                days_to_expiry=max(1, days_to_expiry),
                option_type="put",
            )

            prob_result = self.optimizer.calculate_assignment_probability(
                strike=contract.strike,
                current_price=current_price,
                volatility=volatility,
                days_to_expiry=max(1, days_to_expiry),
                option_type="put",
            )
            assignment_prob = prob_result.probability

            profile = self.optimizer.get_profile_for_sigma(sigma_distance)
        except (ValueError, ZeroDivisionError) as e:
            warnings.append(f"Could not calculate probability: {e}")

        # Check liquidity warnings
        add_liquidity_warnings(contract, warnings, MIN_OPEN_INTEREST, MAX_BID_ASK_SPREAD_PCT)

        # Check for earnings
        if earnings_dates:
            check_earnings_warning(contract.expiration_date, earnings_dates, warnings)

        # Check for ex-dividend and early assignment risk
        if ex_dividend_dates:
            check_early_assignment_risk(contract, current_price, ex_dividend_dates, warnings)

        logger.info(
            f"Analyzed cash-secured put: {contract.strike} strike, "
            f"${premium_per_share:.2f} premium, {assignment_prob * 100 if assignment_prob else 0:.1f}% P(ITM)"
        )

        return CoveredPutResult(
            contract=contract,
            current_price=current_price,
            premium_per_share=premium_per_share,
            total_premium=total_premium,
            collateral_required=collateral_required,
            effective_purchase_price=effective_purchase_price,
            discount_from_current=discount_from_current,
            max_profit=max_profit,
            max_profit_pct=max_profit_pct,
            max_loss=max_loss,
            breakeven=breakeven,
            profit_if_flat=profit_if_flat,
            profit_if_flat_pct=profit_if_flat_pct,
            assignment_probability=assignment_prob,
            days_to_expiry=days_to_expiry,
            annualized_return_if_otm=annualized_if_otm,
            sigma_distance=sigma_distance,
            profile=profile,
            warnings=warnings,
        )

    def get_recommendations(
        self,
        options_chain: OptionsChain,
        current_price: float,
        volatility: float,
        expiration_date: Optional[str] = None,
        profile: Optional[StrikeProfile] = None,
        target_purchase_price: Optional[float] = None,
        min_premium: float = 0.05,
        limit: int = 5,
    ) -> list[CoveredPutResult]:
        """
        Get ranked cash-secured put recommendations.

        Args:
            options_chain: Options chain data
            current_price: Current stock price
            volatility: Annualized volatility
            expiration_date: Specific expiration (None = nearest)
            profile: StrikeProfile to filter by (None = all profiles)
            target_purchase_price: Desired effective purchase price (filters strikes)
            min_premium: Minimum premium per share
            limit: Maximum recommendations to return

        Returns:
            List of CoveredPutResult sorted by annualized return
        """
        puts = options_chain.get_puts()

        # Filter by expiration
        if expiration_date:
            puts = [c for c in puts if c.expiration_date == expiration_date]
        else:
            # Use nearest expiration
            expirations = sorted({c.expiration_date for c in puts})
            if expirations:
                expiration_date = expirations[0]
                puts = [c for c in puts if c.expiration_date == expiration_date]

        if not puts:
            logger.warning("No put contracts found for recommendations")
            return []

        results = []
        for contract in puts:
            # Skip ITM puts
            if contract.strike >= current_price:
                continue

            # Skip zero or low premium (PRD tradability gate)
            if not contract.bid or contract.bid < min_premium:
                continue

            try:
                result = self.analyze(
                    contract=contract, current_price=current_price, volatility=volatility
                )

                # Filter by profile if specified
                if profile and result.profile != profile:
                    continue

                # Filter by target purchase price if specified
                if (
                    target_purchase_price
                    and result.effective_purchase_price > target_purchase_price
                ):
                    continue

                results.append(result)
            except ValueError:
                continue

        # Sort by annualized return if OTM (highest first)
        results.sort(key=lambda r: r.annualized_return_if_otm, reverse=True)

        logger.info(f"Generated {len(results[:limit])} cash-secured put recommendations")
        return results[:limit]

