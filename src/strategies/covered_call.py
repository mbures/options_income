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

from src.warnings import DEFAULT_MAX_BID_ASK_SPREAD_PCT as MAX_BID_ASK_SPREAD_PCT
from src.warnings import DEFAULT_MIN_OPEN_INTEREST as MIN_OPEN_INTEREST

# MIN_BID_PRICE constant (define here if not in warnings)
MIN_BID_PRICE = 0.05  # Minimum bid price for option liquidity
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



class CoveredCallAnalyzer:
    """
    Analyzer for covered call strategies.

    A covered call involves:
    - Owning 100 shares of stock per contract
    - Selling an OTM call option against those shares
    - Collecting premium in exchange for capping upside

    Outcomes:
    - If stock < strike at expiry: Keep shares + premium (profit = premium)
    - If stock >= strike at expiry: Shares called away at strike (profit = premium + (strike - cost_basis))

    Example:
        analyzer = CoveredCallAnalyzer(strike_optimizer)
        result = analyzer.analyze(
            contract=call_option,
            current_price=10.50,
            volatility=0.30,
            shares=100
        )
    """

    def __init__(self, strike_optimizer: StrikeOptimizer):
        """
        Initialize the covered call analyzer.

        Args:
            strike_optimizer: StrikeOptimizer for probability calculations
        """
        self.optimizer = strike_optimizer

    def analyze(
        self,
        contract: OptionContract,
        current_price: float,
        volatility: float,
        shares: int = 100,
        cost_basis: Optional[float] = None,
        earnings_dates: Optional[list[str]] = None,
    ) -> CoveredCallResult:
        """
        Analyze a covered call position.

        Args:
            contract: Call option contract to analyze
            current_price: Current stock price
            volatility: Annualized volatility for calculations
            shares: Number of shares (default 100 per contract)
            cost_basis: Original purchase price (default: current_price)
            earnings_dates: List of earnings dates to check (YYYY-MM-DD)

        Returns:
            CoveredCallResult with all metrics

        Raises:
            ValueError: If contract is not a call or is ITM
        """
        # Validate inputs
        if not contract.is_call:
            raise ValueError("Contract must be a call option")
        if contract.strike <= current_price:
            raise ValueError(
                f"Call strike ({contract.strike}) must be above current price ({current_price})"
            )

        # Use current price as cost basis if not provided
        if cost_basis is None:
            cost_basis = current_price

        warnings = []

        # Calculate days to expiry
        days_to_expiry = calculate_days_to_expiry(contract.expiration_date)

        # Get premium (bid price)
        premium_per_share = contract.bid if contract.bid else 0.0

        # Check for minimum premium
        if premium_per_share < MIN_BID_PRICE:
            warnings.append(f"Low premium: ${premium_per_share:.2f} (minimum ${MIN_BID_PRICE})")

        total_premium = premium_per_share * shares

        # Calculate returns
        # Profit if flat (stock unchanged): just the premium
        profit_if_flat = total_premium
        stock_value = current_price * shares
        profit_if_flat_pct = (profit_if_flat / stock_value) * 100 if stock_value > 0 else 0

        # Max profit if called: premium + (strike - cost_basis) * shares
        appreciation = (contract.strike - cost_basis) * shares
        max_profit = total_premium + appreciation
        max_profit_pct = (max_profit / stock_value) * 100 if stock_value > 0 else 0

        # Breakeven: current price - premium per share
        breakeven = current_price - premium_per_share

        # Annualized returns
        if days_to_expiry > 0:
            annualized_if_flat = (profit_if_flat / stock_value) * (365 / days_to_expiry)
            annualized_if_called = (max_profit / stock_value) * (365 / days_to_expiry)
        else:
            annualized_if_flat = 0
            annualized_if_called = 0

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
                option_type="call",
            )

            prob_result = self.optimizer.calculate_assignment_probability(
                strike=contract.strike,
                current_price=current_price,
                volatility=volatility,
                days_to_expiry=max(1, days_to_expiry),
                option_type="call",
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

        logger.info(
            f"Analyzed covered call: {contract.strike} strike, "
            f"${premium_per_share:.2f} premium, {assignment_prob * 100 if assignment_prob else 0:.1f}% P(ITM)"
        )

        return CoveredCallResult(
            contract=contract,
            current_price=current_price,
            shares=shares,
            premium_per_share=premium_per_share,
            total_premium=total_premium,
            max_profit=max_profit,
            max_profit_pct=max_profit_pct,
            breakeven=breakeven,
            profit_if_flat=profit_if_flat,
            profit_if_flat_pct=profit_if_flat_pct,
            assignment_probability=assignment_prob,
            days_to_expiry=days_to_expiry,
            annualized_return_if_flat=annualized_if_flat,
            annualized_return_if_called=annualized_if_called,
            sigma_distance=sigma_distance,
            profile=profile,
            warnings=warnings,
        )

    def get_recommendations(
        self,
        options_chain: OptionsChain,
        current_price: float,
        volatility: float,
        shares: int = 100,
        cost_basis: Optional[float] = None,
        expiration_date: Optional[str] = None,
        profile: Optional[StrikeProfile] = None,
        min_premium: float = 0.05,
        limit: int = 5,
    ) -> list[CoveredCallResult]:
        """
        Get ranked covered call recommendations.

        Args:
            options_chain: Options chain data
            current_price: Current stock price
            volatility: Annualized volatility
            shares: Number of shares (default 100)
            cost_basis: Original purchase price (default: current_price)
            expiration_date: Specific expiration (None = nearest)
            profile: StrikeProfile to filter by (None = all profiles)
            min_premium: Minimum premium per share
            limit: Maximum recommendations to return

        Returns:
            List of CoveredCallResult sorted by annualized return
        """
        calls = options_chain.get_calls()

        # Filter by expiration
        if expiration_date:
            calls = [c for c in calls if c.expiration_date == expiration_date]
        else:
            # Use nearest expiration
            expirations = sorted({c.expiration_date for c in calls})
            if expirations:
                expiration_date = expirations[0]
                calls = [c for c in calls if c.expiration_date == expiration_date]

        if not calls:
            logger.warning("No call contracts found for recommendations")
            return []

        results = []
        for contract in calls:
            # Skip ITM calls
            if contract.strike <= current_price:
                continue

            # Skip zero or low premium (PRD tradability gate)
            if not contract.bid or contract.bid < min_premium:
                continue

            try:
                result = self.analyze(
                    contract=contract,
                    current_price=current_price,
                    volatility=volatility,
                    shares=shares,
                    cost_basis=cost_basis,
                )

                # Filter by profile if specified
                if profile and result.profile != profile:
                    continue

                results.append(result)
            except ValueError:
                continue

        # Sort by annualized return if flat (highest first)
        results.sort(key=lambda r: r.annualized_return_if_flat, reverse=True)

        logger.info(f"Generated {len(results[:limit])} covered call recommendations")
        return results[:limit]

