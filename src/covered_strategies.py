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
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional, List, Dict, Any

from .models import OptionContract, OptionsChain
from .strike_optimizer import StrikeOptimizer, StrikeProfile, ProbabilityResult

logger = logging.getLogger(__name__)


# Warning thresholds
MAX_BID_ASK_SPREAD_PCT = 10.0  # 10% of mid price
MIN_OPEN_INTEREST = 100
MIN_BID_PRICE = 0.05  # Minimum viable premium


class WheelState(Enum):
    """
    Current state in the wheel strategy cycle.

    The wheel strategy alternates between:
    - CASH: No shares owned, sell cash-secured puts to potentially acquire
    - SHARES: Shares owned (from assignment), sell covered calls to exit or collect premium
    """
    CASH = "cash"       # Ready to sell puts
    SHARES = "shares"   # Ready to sell calls


@dataclass
class CoveredCallResult:
    """
    Result of a covered call analysis.

    Attributes:
        contract: The call option contract analyzed
        current_price: Stock price at time of analysis
        shares: Number of shares covered (typically 100 per contract)
        premium_per_share: Premium received per share (bid price)
        total_premium: Total premium for all shares
        max_profit: Maximum profit if called away (premium + appreciation)
        max_profit_pct: Maximum profit as percentage of stock value
        breakeven: Stock price at breakeven (current - premium)
        profit_if_flat: Profit if stock unchanged at expiry
        profit_if_flat_pct: Flat profit as percentage
        assignment_probability: Probability of being called away
        days_to_expiry: Days until expiration
        annualized_return_if_flat: Annualized return if not called
        annualized_return_if_called: Annualized return if called
        sigma_distance: Distance from current price in sigmas
        profile: Risk profile this strike fits
        warnings: List of warning messages
    """
    contract: OptionContract
    current_price: float
    shares: int
    premium_per_share: float
    total_premium: float
    max_profit: float
    max_profit_pct: float
    breakeven: float
    profit_if_flat: float
    profit_if_flat_pct: float
    assignment_probability: Optional[float]
    days_to_expiry: int
    annualized_return_if_flat: float
    annualized_return_if_called: float
    sigma_distance: Optional[float]
    profile: Optional[StrikeProfile]
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "strike": self.contract.strike,
            "expiration_date": self.contract.expiration_date,
            "current_price": self.current_price,
            "shares": self.shares,
            "premium_per_share": round(self.premium_per_share, 4),
            "total_premium": round(self.total_premium, 2),
            "max_profit": round(self.max_profit, 2),
            "max_profit_pct": round(self.max_profit_pct, 2),
            "breakeven": round(self.breakeven, 4),
            "profit_if_flat": round(self.profit_if_flat, 2),
            "profit_if_flat_pct": round(self.profit_if_flat_pct, 2),
            "assignment_probability_pct": round(self.assignment_probability * 100, 2) if self.assignment_probability else None,
            "days_to_expiry": self.days_to_expiry,
            "annualized_return_if_flat_pct": round(self.annualized_return_if_flat * 100, 2),
            "annualized_return_if_called_pct": round(self.annualized_return_if_called * 100, 2),
            "sigma_distance": round(self.sigma_distance, 2) if self.sigma_distance else None,
            "profile": self.profile.value if self.profile else None,
            "warnings": self.warnings,
        }


@dataclass
class CoveredPutResult:
    """
    Result of a cash-secured put analysis.

    Attributes:
        contract: The put option contract analyzed
        current_price: Stock price at time of analysis
        premium_per_share: Premium received per share (bid price)
        total_premium: Total premium for contract
        collateral_required: Cash required to secure the put (strike × 100)
        effective_purchase_price: Net cost if assigned (strike - premium)
        discount_from_current: Percentage discount from current price if assigned
        max_profit: Maximum profit if OTM at expiry (premium)
        max_profit_pct: Max profit as percentage of collateral
        max_loss: Maximum loss if stock goes to zero
        breakeven: Stock price at breakeven (strike - premium)
        profit_if_flat: Profit if stock unchanged at expiry (premium)
        profit_if_flat_pct: Flat profit as percentage of collateral
        assignment_probability: Probability of being assigned
        days_to_expiry: Days until expiration
        annualized_return_if_otm: Annualized return if not assigned
        sigma_distance: Distance from current price in sigmas
        profile: Risk profile this strike fits
        warnings: List of warning messages
    """
    contract: OptionContract
    current_price: float
    premium_per_share: float
    total_premium: float
    collateral_required: float
    effective_purchase_price: float
    discount_from_current: float
    max_profit: float
    max_profit_pct: float
    max_loss: float
    breakeven: float
    profit_if_flat: float
    profit_if_flat_pct: float
    assignment_probability: Optional[float]
    days_to_expiry: int
    annualized_return_if_otm: float
    sigma_distance: Optional[float]
    profile: Optional[StrikeProfile]
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "strike": self.contract.strike,
            "expiration_date": self.contract.expiration_date,
            "current_price": self.current_price,
            "premium_per_share": round(self.premium_per_share, 4),
            "total_premium": round(self.total_premium, 2),
            "collateral_required": round(self.collateral_required, 2),
            "effective_purchase_price": round(self.effective_purchase_price, 4),
            "discount_from_current_pct": round(self.discount_from_current * 100, 2),
            "max_profit": round(self.max_profit, 2),
            "max_profit_pct": round(self.max_profit_pct, 2),
            "max_loss": round(self.max_loss, 2),
            "breakeven": round(self.breakeven, 4),
            "profit_if_flat": round(self.profit_if_flat, 2),
            "profit_if_flat_pct": round(self.profit_if_flat_pct, 2),
            "assignment_probability_pct": round(self.assignment_probability * 100, 2) if self.assignment_probability else None,
            "days_to_expiry": self.days_to_expiry,
            "annualized_return_if_otm_pct": round(self.annualized_return_if_otm * 100, 2),
            "sigma_distance": round(self.sigma_distance, 2) if self.sigma_distance else None,
            "profile": self.profile.value if self.profile else None,
            "warnings": self.warnings,
        }


@dataclass
class WheelRecommendation:
    """
    Recommendation for wheel strategy action.

    Attributes:
        state: Current wheel state (CASH or SHARES)
        action: Recommended action ("sell_put" or "sell_call")
        analysis: The analysis result (CoveredCallResult or CoveredPutResult)
        rationale: Explanation of the recommendation
    """
    state: WheelState
    action: str
    analysis: Any  # CoveredCallResult or CoveredPutResult
    rationale: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "state": self.state.value,
            "action": self.action,
            "analysis": self.analysis.to_dict() if self.analysis else None,
            "rationale": self.rationale,
        }


@dataclass
class WheelCycleMetrics:
    """
    Metrics for tracking a complete wheel cycle.

    Attributes:
        total_premium_collected: Sum of all premiums from puts and calls
        num_put_cycles: Number of puts sold
        num_call_cycles: Number of calls sold
        shares_acquired_price: Price paid when assigned on put (None if not assigned)
        shares_sold_price: Price received when called away (None if not called)
        average_cost_basis: Adjusted cost basis after premiums
        net_profit: Total profit/loss for the cycle
        cycle_complete: Whether the cycle is complete (shares sold)
    """
    total_premium_collected: float = 0.0
    num_put_cycles: int = 0
    num_call_cycles: int = 0
    shares_acquired_price: Optional[float] = None
    shares_sold_price: Optional[float] = None
    average_cost_basis: Optional[float] = None
    net_profit: Optional[float] = None
    cycle_complete: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total_premium_collected": round(self.total_premium_collected, 2),
            "num_put_cycles": self.num_put_cycles,
            "num_call_cycles": self.num_call_cycles,
            "shares_acquired_price": round(self.shares_acquired_price, 4) if self.shares_acquired_price else None,
            "shares_sold_price": round(self.shares_sold_price, 4) if self.shares_sold_price else None,
            "average_cost_basis": round(self.average_cost_basis, 4) if self.average_cost_basis else None,
            "net_profit": round(self.net_profit, 2) if self.net_profit else None,
            "cycle_complete": self.cycle_complete,
        }


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
        earnings_dates: Optional[List[str]] = None
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
            raise ValueError(f"Call strike ({contract.strike}) must be above current price ({current_price})")

        # Use current price as cost basis if not provided
        if cost_basis is None:
            cost_basis = current_price

        warnings = []

        # Calculate days to expiry
        days_to_expiry = self._calculate_days_to_expiry(contract.expiration_date)

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
                option_type="call"
            )

            prob_result = self.optimizer.calculate_assignment_probability(
                strike=contract.strike,
                current_price=current_price,
                volatility=volatility,
                days_to_expiry=max(1, days_to_expiry),
                option_type="call"
            )
            assignment_prob = prob_result.probability

            profile = self.optimizer.get_profile_for_sigma(sigma_distance)
        except (ValueError, ZeroDivisionError) as e:
            warnings.append(f"Could not calculate probability: {e}")

        # Check liquidity warnings
        self._add_liquidity_warnings(contract, warnings)

        # Check for earnings
        if earnings_dates:
            self._check_earnings_warning(contract.expiration_date, earnings_dates, warnings)

        logger.info(
            f"Analyzed covered call: {contract.strike} strike, "
            f"${premium_per_share:.2f} premium, {assignment_prob*100 if assignment_prob else 0:.1f}% P(ITM)"
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
        limit: int = 5
    ) -> List[CoveredCallResult]:
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
            expirations = sorted(set(c.expiration_date for c in calls))
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
                    cost_basis=cost_basis
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

    def _calculate_days_to_expiry(self, expiration_date: str) -> int:
        """
        Calculate calendar days until expiration.

        Uses calendar days (not trading days) as this is the standard
        convention for options pricing (Black-Scholes, IV term structure).

        Example: Jan 19 to Jan 23 = 4 calendar days
        """
        try:
            exp_date_obj = date.fromisoformat(expiration_date)
            today = date.today()
            days = (exp_date_obj - today).days
            return max(1, days)
        except (ValueError, TypeError):
            return 30  # Default fallback

    def _add_liquidity_warnings(self, contract: OptionContract, warnings: List[str]) -> None:
        """Add warnings for liquidity issues."""
        if contract.open_interest is not None and contract.open_interest < MIN_OPEN_INTEREST:
            warnings.append(f"Low open interest: {contract.open_interest}")

        if contract.bid is not None and contract.ask is not None:
            mid = (contract.bid + contract.ask) / 2
            if mid > 0:
                spread_pct = ((contract.ask - contract.bid) / mid) * 100
                if spread_pct > MAX_BID_ASK_SPREAD_PCT:
                    warnings.append(f"Wide bid-ask spread: {spread_pct:.1f}%")

        if contract.bid is None or contract.bid <= 0:
            warnings.append("No bid price available")

    def _check_earnings_warning(
        self,
        expiration_date: str,
        earnings_dates: List[str],
        warnings: List[str]
    ) -> None:
        """Check if expiration spans an earnings date."""
        try:
            exp_dt = datetime.fromisoformat(expiration_date)
            now = datetime.now()

            for earn_date in earnings_dates:
                earn_dt = datetime.fromisoformat(earn_date)
                if now <= earn_dt <= exp_dt:
                    warnings.append(f"Expiration spans earnings date: {earn_date}")
                    break
        except (ValueError, TypeError):
            pass


class CoveredPutAnalyzer:
    """
    Analyzer for cash-secured put strategies.

    A cash-secured put involves:
    - Setting aside cash equal to strike × 100 per contract
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
        earnings_dates: Optional[List[str]] = None,
        ex_dividend_dates: Optional[List[str]] = None
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
            raise ValueError(f"Put strike ({contract.strike}) must be below current price ({current_price})")

        warnings = []

        # Calculate days to expiry
        days_to_expiry = self._calculate_days_to_expiry(contract.expiration_date)

        # Get premium (bid price)
        premium_per_share = contract.bid if contract.bid else 0.0

        # Check for minimum premium
        if premium_per_share < MIN_BID_PRICE:
            warnings.append(f"Low premium: ${premium_per_share:.2f} (minimum ${MIN_BID_PRICE})")

        # Standard contract size
        shares_per_contract = 100
        total_premium = premium_per_share * shares_per_contract

        # Collateral required: strike × 100
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
        profit_if_flat_pct = (profit_if_flat / collateral_required) * 100 if collateral_required > 0 else 0

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
                option_type="put"
            )

            prob_result = self.optimizer.calculate_assignment_probability(
                strike=contract.strike,
                current_price=current_price,
                volatility=volatility,
                days_to_expiry=max(1, days_to_expiry),
                option_type="put"
            )
            assignment_prob = prob_result.probability

            profile = self.optimizer.get_profile_for_sigma(sigma_distance)
        except (ValueError, ZeroDivisionError) as e:
            warnings.append(f"Could not calculate probability: {e}")

        # Check liquidity warnings
        self._add_liquidity_warnings(contract, warnings)

        # Check for earnings
        if earnings_dates:
            self._check_earnings_warning(contract.expiration_date, earnings_dates, warnings)

        # Check for ex-dividend and early assignment risk
        if ex_dividend_dates:
            self._check_early_assignment_risk(
                contract, current_price, ex_dividend_dates, warnings
            )

        logger.info(
            f"Analyzed cash-secured put: {contract.strike} strike, "
            f"${premium_per_share:.2f} premium, {assignment_prob*100 if assignment_prob else 0:.1f}% P(ITM)"
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
        limit: int = 5
    ) -> List[CoveredPutResult]:
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
            expirations = sorted(set(c.expiration_date for c in puts))
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
                    contract=contract,
                    current_price=current_price,
                    volatility=volatility
                )

                # Filter by profile if specified
                if profile and result.profile != profile:
                    continue

                # Filter by target purchase price if specified
                if target_purchase_price and result.effective_purchase_price > target_purchase_price:
                    continue

                results.append(result)
            except ValueError:
                continue

        # Sort by annualized return if OTM (highest first)
        results.sort(key=lambda r: r.annualized_return_if_otm, reverse=True)

        logger.info(f"Generated {len(results[:limit])} cash-secured put recommendations")
        return results[:limit]

    def _calculate_days_to_expiry(self, expiration_date: str) -> int:
        """
        Calculate calendar days until expiration.

        Uses calendar days (not trading days) as this is the standard
        convention for options pricing (Black-Scholes, IV term structure).

        Example: Jan 19 to Jan 23 = 4 calendar days
        """
        try:
            exp_date_obj = date.fromisoformat(expiration_date)
            today = date.today()
            days = (exp_date_obj - today).days
            return max(1, days)
        except (ValueError, TypeError):
            return 30  # Default fallback

    def _add_liquidity_warnings(self, contract: OptionContract, warnings: List[str]) -> None:
        """Add warnings for liquidity issues."""
        if contract.open_interest is not None and contract.open_interest < MIN_OPEN_INTEREST:
            warnings.append(f"Low open interest: {contract.open_interest}")

        if contract.bid is not None and contract.ask is not None:
            mid = (contract.bid + contract.ask) / 2
            if mid > 0:
                spread_pct = ((contract.ask - contract.bid) / mid) * 100
                if spread_pct > MAX_BID_ASK_SPREAD_PCT:
                    warnings.append(f"Wide bid-ask spread: {spread_pct:.1f}%")

        if contract.bid is None or contract.bid <= 0:
            warnings.append("No bid price available")

    def _check_earnings_warning(
        self,
        expiration_date: str,
        earnings_dates: List[str],
        warnings: List[str]
    ) -> None:
        """Check if expiration spans an earnings date."""
        try:
            exp_dt = datetime.fromisoformat(expiration_date)
            now = datetime.now()

            for earn_date in earnings_dates:
                earn_dt = datetime.fromisoformat(earn_date)
                if now <= earn_dt <= exp_dt:
                    warnings.append(f"Expiration spans earnings date: {earn_date}")
                    break
        except (ValueError, TypeError):
            pass

    def _check_early_assignment_risk(
        self,
        contract: OptionContract,
        current_price: float,
        ex_dividend_dates: List[str],
        warnings: List[str]
    ) -> None:
        """
        Check for early assignment risk on deep ITM puts near ex-dividend.

        Early assignment is more likely when:
        - Put is deep ITM (intrinsic value high)
        - Ex-dividend date is before expiration
        - Time value is low relative to dividend
        """
        try:
            exp_dt = datetime.fromisoformat(contract.expiration_date)
            now = datetime.now()

            for ex_date in ex_dividend_dates:
                ex_dt = datetime.fromisoformat(ex_date)
                if now <= ex_dt <= exp_dt:
                    # Check if put is significantly ITM
                    # This is for ITM puts that might get early exercised
                    # Note: For OTM puts this is less of a concern
                    intrinsic_value = contract.strike - current_price
                    if intrinsic_value > 0:
                        # Put is ITM, warn about early assignment
                        warnings.append(
                            f"Elevated early assignment risk: ex-dividend {ex_date}, "
                            f"put is ${intrinsic_value:.2f} ITM"
                        )
                    break
        except (ValueError, TypeError):
            pass


class WheelStrategy:
    """
    Manager for the wheel strategy.

    The wheel strategy cycles between:
    1. Sell cash-secured puts → potentially acquire shares at discount
    2. Sell covered calls → potentially exit position at profit

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

    def __init__(
        self,
        call_analyzer: CoveredCallAnalyzer,
        put_analyzer: CoveredPutAnalyzer
    ):
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
        profile: Optional[StrikeProfile] = None
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
                profile=profile
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
                profile=profile
            )

    def _recommend_put(
        self,
        options_chain: OptionsChain,
        current_price: float,
        volatility: float,
        expiration_date: Optional[str],
        profile: Optional[StrikeProfile]
    ) -> Optional[WheelRecommendation]:
        """Generate put recommendation for CASH state."""
        recommendations = self.put_analyzer.get_recommendations(
            options_chain=options_chain,
            current_price=current_price,
            volatility=volatility,
            expiration_date=expiration_date,
            profile=profile or StrikeProfile.MODERATE,
            limit=1
        )

        if not recommendations:
            return None

        best = recommendations[0]
        rationale = (
            f"Sell {best.contract.strike} put for ${best.premium_per_share:.2f} premium. "
            f"If assigned, acquire shares at ${best.effective_purchase_price:.2f} "
            f"({best.discount_from_current*100:.1f}% below current). "
            f"If OTM, keep ${best.total_premium:.2f} premium "
            f"({best.annualized_return_if_otm*100:.1f}% annualized)."
        )

        return WheelRecommendation(
            state=WheelState.CASH,
            action="sell_put",
            analysis=best,
            rationale=rationale
        )

    def _recommend_call(
        self,
        options_chain: OptionsChain,
        current_price: float,
        volatility: float,
        shares: int,
        cost_basis: Optional[float],
        expiration_date: Optional[str],
        profile: Optional[StrikeProfile]
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
            limit=1
        )

        if not recommendations:
            return None

        best = recommendations[0]
        rationale = (
            f"Sell {best.contract.strike} call for ${best.premium_per_share:.2f} premium. "
            f"If called away, profit ${best.max_profit:.2f} ({best.max_profit_pct:.1f}%). "
            f"If OTM, keep ${best.total_premium:.2f} premium "
            f"({best.annualized_return_if_flat*100:.1f}% annualized)."
        )

        return WheelRecommendation(
            state=WheelState.SHARES,
            action="sell_call",
            analysis=best,
            rationale=rationale
        )

    def calculate_cycle_metrics(
        self,
        premiums_collected: List[float],
        acquisition_price: Optional[float] = None,
        sale_price: Optional[float] = None,
        num_puts: int = 0,
        num_calls: int = 0
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
