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

from .constants import MAX_BID_ASK_SPREAD_PCT, MIN_BID_PRICE, MIN_OPEN_INTEREST
from .models import (
    CoveredCallResult,
    CoveredPutResult,
    OptionContract,
    OptionsChain,
    WheelCycleMetrics,
    WheelRecommendation,
    WheelState,
)
from .strike_optimizer import StrikeOptimizer, StrikeProfile
from .utils import calculate_days_to_expiry
from .warnings import add_liquidity_warnings, check_early_assignment_risk, check_earnings_warning

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

            # Skip low premium
            if contract.bid and contract.bid < min_premium:
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

            # Skip low premium
            if contract.bid and contract.bid < min_premium:
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
