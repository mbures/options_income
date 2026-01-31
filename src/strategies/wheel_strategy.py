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



class WheelStrategy:
    """
    Manager for the wheel strategy.

    The wheel strategy cycles between:
    1. Sell cash-secured puts -> potentially acquire shares at discount
    2. Sell covered calls -> potentially exit position at profit

    The strategy continuously collects premium regardless of whether
    options are assigned or expire worthless.

    Example:
        wheel = WheelStrategy(call_analyzer, put_analyzer)

        # Get recommendation based on current state
        rec = wheel.get_recommendation(
            state=WheelState.CASH,
            options_chain=chain,
            current_price=10.50,
            volatility=0.30
        )
    """

    def __init__(self, call_analyzer: CoveredCallAnalyzer, put_analyzer: CoveredPutAnalyzer):
        """
        Initialize the wheel strategy manager.

        Args:
            call_analyzer: CoveredCallAnalyzer for call analysis
            put_analyzer: CoveredPutAnalyzer for put analysis
        """
        self.call_analyzer = call_analyzer
        self.put_analyzer = put_analyzer

    def get_recommendation(
        self,
        state: WheelState,
        options_chain: OptionsChain,
        current_price: float,
        volatility: float,
        shares: int = 100,
        cost_basis: Optional[float] = None,
        expiration_date: Optional[str] = None,
        profile: Optional[StrikeProfile] = None,
    ) -> Optional[WheelRecommendation]:
        """
        Get a recommendation based on current wheel state.

        Args:
            state: Current state (CASH or SHARES)
            options_chain: Options chain data
            current_price: Current stock price
            volatility: Annualized volatility
            shares: Number of shares (default 100)
            cost_basis: Cost basis if holding shares (for SHARES state)
            expiration_date: Specific expiration (None = nearest)
            profile: StrikeProfile preference

        Returns:
            WheelRecommendation with suggested action and analysis
        """
        if state == WheelState.CASH:
            # Holding cash - recommend selling a put
            return self._recommend_put(
                options_chain=options_chain,
                current_price=current_price,
                volatility=volatility,
                expiration_date=expiration_date,
                profile=profile,
            )
        else:
            # Holding shares - recommend selling a call
            return self._recommend_call(
                options_chain=options_chain,
                current_price=current_price,
                volatility=volatility,
                shares=shares,
                cost_basis=cost_basis,
                expiration_date=expiration_date,
                profile=profile,
            )

    def _recommend_put(
        self,
        options_chain: OptionsChain,
        current_price: float,
        volatility: float,
        expiration_date: Optional[str],
        profile: Optional[StrikeProfile],
    ) -> Optional[WheelRecommendation]:
        """Generate put recommendation for CASH state."""
        recommendations = self.put_analyzer.get_recommendations(
            options_chain=options_chain,
            current_price=current_price,
            volatility=volatility,
            expiration_date=expiration_date,
            profile=profile or StrikeProfile.MODERATE,
            limit=1,
        )

        if not recommendations:
            return None

        best = recommendations[0]
        rationale = (
            f"Sell {best.contract.strike} put for ${best.premium_per_share:.2f} premium. "
            f"If assigned, acquire shares at ${best.effective_purchase_price:.2f} "
            f"({best.discount_from_current * 100:.1f}% below current). "
            f"If OTM, keep ${best.total_premium:.2f} premium "
            f"({best.annualized_return_if_otm * 100:.1f}% annualized)."
        )

        return WheelRecommendation(
            state=WheelState.CASH, action="sell_put", analysis=best, rationale=rationale
        )

    def _recommend_call(
        self,
        options_chain: OptionsChain,
        current_price: float,
        volatility: float,
        shares: int,
        cost_basis: Optional[float],
        expiration_date: Optional[str],
        profile: Optional[StrikeProfile],
    ) -> Optional[WheelRecommendation]:
        """Generate call recommendation for SHARES state."""
        recommendations = self.call_analyzer.get_recommendations(
            options_chain=options_chain,
            current_price=current_price,
            volatility=volatility,
            shares=shares,
            cost_basis=cost_basis,
            expiration_date=expiration_date,
            profile=profile or StrikeProfile.MODERATE,
            limit=1,
        )

        if not recommendations:
            return None

        best = recommendations[0]
        rationale = (
            f"Sell {best.contract.strike} call for ${best.premium_per_share:.2f} premium. "
            f"If called away, profit ${best.max_profit:.2f} ({best.max_profit_pct:.1f}%). "
            f"If OTM, keep ${best.total_premium:.2f} premium "
            f"({best.annualized_return_if_flat * 100:.1f}% annualized)."
        )

        return WheelRecommendation(
            state=WheelState.SHARES, action="sell_call", analysis=best, rationale=rationale
        )

    def calculate_cycle_metrics(
        self,
        premiums_collected: list[float],
        acquisition_price: Optional[float] = None,
        sale_price: Optional[float] = None,
        num_puts: int = 0,
        num_calls: int = 0,
    ) -> WheelCycleMetrics:
        """
        Calculate metrics for a wheel cycle.

        Args:
            premiums_collected: List of all premiums received
            acquisition_price: Strike price where shares were assigned (if any)
            sale_price: Strike price where shares were called away (if any)
            num_puts: Number of put cycles
            num_calls: Number of call cycles

        Returns:
            WheelCycleMetrics with cycle statistics
        """
        total_premium = sum(premiums_collected)

        metrics = WheelCycleMetrics(
            total_premium_collected=total_premium,
            num_put_cycles=num_puts,
            num_call_cycles=num_calls,
        )

        if acquisition_price is not None:
            metrics.shares_acquired_price = acquisition_price
            # Cost basis = strike - total premium per share
            premium_per_share = total_premium / 100  # Assuming standard contract
            metrics.average_cost_basis = acquisition_price - premium_per_share

        if sale_price is not None:
            metrics.shares_sold_price = sale_price
            metrics.cycle_complete = True

            if metrics.average_cost_basis is not None:
                # Net profit = (sale price - cost basis) * 100 shares
                metrics.net_profit = (sale_price - metrics.average_cost_basis) * 100

        return metrics
