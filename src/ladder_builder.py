"""
Ladder Builder for covered call/put positions across multiple weekly expirations.

This module provides laddered position building capabilities for covered options:
- Weekly expiration detection (Friday/Wednesday/Monday weeklies)
- Position allocation strategies (Equal, FrontWeighted, BackWeighted)
- Strike adjustment by week (sigma scaling)
- Complete ladder generation with metrics

The goal is to spread premium collection across multiple weeks, reducing
timing risk and providing more consistent income generation.

Example:
    from src.ladder_builder import LadderBuilder, AllocationStrategy, LadderConfig

    builder = LadderBuilder(
        finnhub_client=client,
        strike_optimizer=optimizer,
        config=LadderConfig(
            allocation_strategy=AllocationStrategy.EQUAL,
            weeks_to_ladder=4
        )
    )

    result = builder.build_ladder(
        symbol="AAPL",
        shares=400,
        current_price=185.50,
        volatility=0.25,
        options_chain=chain,
        option_type="call"
    )
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Optional

from .models import OptionContract, OptionsChain
from .overlay_scanner import EarningsCalendar
from .strike_optimizer import StrikeOptimizer, StrikeProfile

logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Constants
# =============================================================================


class AllocationStrategy(Enum):
    """
    Position allocation strategies across weekly expirations.

    EQUAL: Distribute shares equally across all weeks.
        Example: 400 shares, 4 weeks -> 100 shares (1 contract) per week

    FRONT_WEIGHTED: Allocate more shares to near-term expirations.
        Rationale: Higher theta decay in near-term, capture premium faster
        Example: 400 shares, 4 weeks -> 160, 120, 80, 40 shares

    BACK_WEIGHTED: Allocate more shares to far-term expirations.
        Rationale: Higher premiums further out, less rebalancing work
        Example: 400 shares, 4 weeks -> 40, 80, 120, 160 shares
    """

    EQUAL = "equal"
    FRONT_WEIGHTED = "front_weighted"
    BACK_WEIGHTED = "back_weighted"


class WeeklyExpirationDay(Enum):
    """Days of the week when weekly options expire."""

    FRIDAY = 4  # Standard weekly options
    WEDNESDAY = 2  # Some index options (VIX, SPX)
    MONDAY = 0  # Some ETF weeklies


# Standard allocation weights for non-equal strategies
# These are relative weights that get normalized to sum to 1.0
ALLOCATION_WEIGHTS = {
    AllocationStrategy.FRONT_WEIGHTED: [4, 3, 2, 1],  # Near-term gets more
    AllocationStrategy.BACK_WEIGHTED: [1, 2, 3, 4],  # Far-term gets more
}


# =============================================================================
# Data Models
# =============================================================================


@dataclass
class LadderConfig:
    """
    Configuration for ladder building.

    Attributes:
        allocation_strategy: How to allocate shares across weeks
        weeks_to_ladder: Number of weekly expirations to include (default 4)
        base_sigma: Base sigma level for strike selection (default 1.5)
        sigma_adjustment_per_week: Sigma adjustment per week from baseline
            Week 1: base_sigma - sigma_adjustment (more aggressive)
            Week 2-3: base_sigma (baseline)
            Week 4+: base_sigma + sigma_adjustment (more conservative)
        min_contracts_per_leg: Minimum contracts per ladder leg (default 1)
        skip_earnings_weeks: Whether to skip weeks with earnings (default True)
        overwrite_cap_pct: Max percentage of shares to use (default 100% for ladders)
        strike_profile: Default strike profile for recommendations
    """

    allocation_strategy: AllocationStrategy = AllocationStrategy.EQUAL
    weeks_to_ladder: int = 4
    base_sigma: float = 1.5
    sigma_adjustment_per_week: float = 0.25
    min_contracts_per_leg: int = 1
    skip_earnings_weeks: bool = True
    overwrite_cap_pct: float = 100.0
    strike_profile: StrikeProfile = StrikeProfile.CONSERVATIVE

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.weeks_to_ladder < 1:
            raise ValueError(f"weeks_to_ladder must be >= 1, got {self.weeks_to_ladder}")
        if self.base_sigma <= 0:
            raise ValueError(f"base_sigma must be > 0, got {self.base_sigma}")
        if self.sigma_adjustment_per_week < 0:
            raise ValueError(
                f"sigma_adjustment_per_week must be >= 0, got {self.sigma_adjustment_per_week}"
            )
        if not 0 < self.overwrite_cap_pct <= 100:
            raise ValueError(
                f"overwrite_cap_pct must be between 0 and 100, got {self.overwrite_cap_pct}"
            )


@dataclass
class LadderLeg:
    """
    A single leg of a ladder position.

    Attributes:
        week_number: Week index (1 = nearest expiration)
        expiration_date: Option expiration date (YYYY-MM-DD)
        days_to_expiry: Calendar days until expiration
        strike: Recommended strike price
        sigma_used: Sigma level used for strike calculation
        contracts: Number of contracts for this leg
        shares_covered: Number of shares covered (contracts × 100)
        option_contract: Selected option contract (if available)
        bid: Bid price of the option
        ask: Ask price of the option
        mid_price: Mid-point of bid/ask
        gross_premium: Expected premium (bid × 100 × contracts)
        delta: Option delta
        p_itm: Probability of finishing ITM
        earnings_warning: Whether this leg spans earnings
        warnings: List of warnings for this leg
        is_actionable: Whether this leg can be executed
        rejection_reason: Reason if not actionable
    """

    week_number: int
    expiration_date: str
    days_to_expiry: int
    strike: float
    sigma_used: float
    contracts: int
    shares_covered: int
    option_contract: Optional[OptionContract] = None
    bid: float = 0.0
    ask: float = 0.0
    mid_price: float = 0.0
    gross_premium: float = 0.0
    delta: float = 0.0
    p_itm: float = 0.0
    earnings_warning: bool = False
    warnings: list[str] = field(default_factory=list)
    is_actionable: bool = True
    rejection_reason: Optional[str] = None

    @property
    def annualized_yield_pct(self) -> float:
        """Calculate simple annualized yield."""
        if self.shares_covered > 0 and self.strike > 0 and self.days_to_expiry > 0:
            notional = self.strike * self.shares_covered
            return (self.gross_premium / notional) * (365 / self.days_to_expiry) * 100
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "week_number": self.week_number,
            "expiration_date": self.expiration_date,
            "days_to_expiry": self.days_to_expiry,
            "strike": round(self.strike, 2),
            "sigma_used": round(self.sigma_used, 3),
            "contracts": self.contracts,
            "shares_covered": self.shares_covered,
            "bid": round(self.bid, 2),
            "ask": round(self.ask, 2),
            "mid_price": round(self.mid_price, 2),
            "gross_premium": round(self.gross_premium, 2),
            "delta": round(self.delta, 4),
            "p_itm_pct": round(self.p_itm * 100, 2),
            "annualized_yield_pct": round(self.annualized_yield_pct, 2),
            "earnings_warning": self.earnings_warning,
            "warnings": self.warnings,
            "is_actionable": self.is_actionable,
            "rejection_reason": self.rejection_reason,
        }


@dataclass
class LadderResult:
    """
    Complete result of ladder building.

    Attributes:
        symbol: Stock symbol
        option_type: "call" or "put"
        current_price: Current stock price
        volatility: Annualized volatility used
        total_shares: Total shares in position
        shares_to_ladder: Shares included in ladder (after cap)
        total_contracts: Total contracts across all legs
        legs: List of ladder legs
        total_gross_premium: Sum of gross premiums across legs
        total_net_premium: Estimated net premium after costs
        weighted_avg_delta: Weighted average delta across legs
        weighted_avg_dte: Weighted average days to expiry
        weighted_avg_yield_pct: Weighted average annualized yield
        earnings_dates: Earnings dates found in range
        warnings: General warnings for the ladder
        config_used: Configuration used for building
    """

    symbol: str
    option_type: str
    current_price: float
    volatility: float
    total_shares: int
    shares_to_ladder: int
    total_contracts: int
    legs: list[LadderLeg]
    total_gross_premium: float
    total_net_premium: float
    weighted_avg_delta: float
    weighted_avg_dte: float
    weighted_avg_yield_pct: float
    earnings_dates: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    config_used: Optional[LadderConfig] = None

    @property
    def actionable_legs(self) -> list[LadderLeg]:
        """Return only actionable legs."""
        return [leg for leg in self.legs if leg.is_actionable]

    @property
    def actionable_count(self) -> int:
        """Number of actionable legs."""
        return len(self.actionable_legs)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "symbol": self.symbol,
            "option_type": self.option_type,
            "current_price": round(self.current_price, 2),
            "volatility": round(self.volatility, 4),
            "total_shares": self.total_shares,
            "shares_to_ladder": self.shares_to_ladder,
            "total_contracts": self.total_contracts,
            "actionable_legs": self.actionable_count,
            "total_legs": len(self.legs),
            "legs": [leg.to_dict() for leg in self.legs],
            "total_gross_premium": round(self.total_gross_premium, 2),
            "total_net_premium": round(self.total_net_premium, 2),
            "weighted_avg_delta": round(self.weighted_avg_delta, 4),
            "weighted_avg_dte": round(self.weighted_avg_dte, 1),
            "weighted_avg_yield_pct": round(self.weighted_avg_yield_pct, 2),
            "earnings_dates": self.earnings_dates,
            "warnings": self.warnings,
        }


# =============================================================================
# Ladder Builder
# =============================================================================


class LadderBuilder:
    """
    Builds laddered covered call/put positions across multiple weekly expirations.

    A ladder spreads contracts across multiple expiration weeks, providing:
    - Reduced timing risk vs. single expiration
    - More consistent weekly income as legs roll
    - Flexibility to adjust strikes week-by-week

    Example:
        builder = LadderBuilder(client, optimizer, LadderConfig())

        result = builder.build_ladder(
            symbol="AAPL",
            shares=400,
            current_price=185.50,
            volatility=0.25,
            options_chain=chain,
            option_type="call"
        )

        for leg in result.actionable_legs:
            print(f"Week {leg.week_number}: {leg.contracts}x ${leg.strike} @ ${leg.bid}")
    """

    def __init__(
        self,
        finnhub_client: Any,
        strike_optimizer: StrikeOptimizer,
        config: Optional[LadderConfig] = None,
    ):
        """
        Initialize the ladder builder.

        Args:
            finnhub_client: FinnhubClient for API calls
            strike_optimizer: StrikeOptimizer for strike/probability calculations
            config: Ladder configuration (uses defaults if None)
        """
        self.finnhub_client = finnhub_client
        self.optimizer = strike_optimizer
        self.config = config or LadderConfig()
        self.earnings_calendar = EarningsCalendar(finnhub_client)

        logger.info(
            f"LadderBuilder initialized: strategy={self.config.allocation_strategy.value}, "
            f"weeks={self.config.weeks_to_ladder}, base_sigma={self.config.base_sigma}"
        )

    def get_weekly_expirations(
        self,
        options_chain: OptionsChain,
        from_date: Optional[date] = None,
        weeks: Optional[int] = None,
    ) -> list[str]:
        """
        Get weekly expiration dates from options chain.

        Identifies Friday weeklies (standard), Wednesday weeklies (index),
        and Monday weeklies (some ETFs). Returns dates sorted by proximity.

        Args:
            options_chain: Options chain to scan for expirations
            from_date: Start date (default: today)
            weeks: Number of weeks to return (default: config.weeks_to_ladder)

        Returns:
            List of expiration dates (YYYY-MM-DD) sorted by date
        """
        if from_date is None:
            from_date = date.today()

        if weeks is None:
            weeks = self.config.weeks_to_ladder

        # Get all calls or puts to find expirations
        contracts = options_chain.get_calls() or options_chain.get_puts()
        if not contracts:
            logger.warning("No contracts in options chain")
            return []

        # Extract unique expiration dates
        all_expirations = set()
        for contract in contracts:
            if contract.expiration_date:
                all_expirations.add(contract.expiration_date)

        # Filter to future expirations and sort
        future_expirations = []
        for exp_str in all_expirations:
            try:
                exp_date = date.fromisoformat(exp_str)
                if exp_date > from_date:
                    future_expirations.append(exp_str)
            except ValueError:
                continue

        future_expirations.sort()

        # Filter to weekly expirations (Friday, Wednesday, Monday)
        # Most options expire on Friday, but some indexes/ETFs have other days
        weekly_expirations = []
        for exp_str in future_expirations:
            exp_date = date.fromisoformat(exp_str)
            day_of_week = exp_date.weekday()

            # Accept Friday (4), Wednesday (2), or Monday (0) expirations
            if day_of_week in (
                WeeklyExpirationDay.FRIDAY.value,
                WeeklyExpirationDay.WEDNESDAY.value,
                WeeklyExpirationDay.MONDAY.value,
            ):
                weekly_expirations.append(exp_str)

        # Return requested number of weeks
        result = weekly_expirations[:weeks]

        logger.debug(f"Found {len(result)} weekly expirations: {result}")
        return result

    def calculate_allocations(
        self, total_shares: int, num_weeks: int, strategy: Optional[AllocationStrategy] = None
    ) -> list[int]:
        """
        Calculate share allocations across weeks.

        Allocations are rounded to contract boundaries (100 shares).
        Rounding residuals are distributed starting from the first week.

        Args:
            total_shares: Total shares to allocate
            num_weeks: Number of weeks to allocate across
            strategy: Allocation strategy (default: config.allocation_strategy)

        Returns:
            List of share counts per week, summing to <= total_shares
        """
        if strategy is None:
            strategy = self.config.allocation_strategy

        if num_weeks <= 0:
            return []

        if total_shares < 100:
            return [0] * num_weeks

        # Apply overwrite cap
        capped_shares = int(total_shares * self.config.overwrite_cap_pct / 100)
        # Round down to contract boundary
        capped_shares = (capped_shares // 100) * 100

        if strategy == AllocationStrategy.EQUAL:
            # Equal distribution
            base_allocation = capped_shares // num_weeks
            # Round to contract boundary
            base_allocation = (base_allocation // 100) * 100

            allocations = [base_allocation] * num_weeks

        else:
            # Weighted distribution (front or back weighted)
            weights = ALLOCATION_WEIGHTS.get(strategy, [1] * num_weeks)

            # Extend or truncate weights to match num_weeks
            if len(weights) < num_weeks:
                # Extend with last weight
                weights = weights + [weights[-1]] * (num_weeks - len(weights))
            elif len(weights) > num_weeks:
                weights = weights[:num_weeks]

            # Normalize weights
            total_weight = sum(weights)
            normalized_weights = [w / total_weight for w in weights]

            # Calculate raw allocations
            raw_allocations = [capped_shares * w for w in normalized_weights]

            # Round down to contract boundaries
            allocations = [(int(a) // 100) * 100 for a in raw_allocations]

        # Distribute any remaining shares (from rounding) to first weeks
        allocated = sum(allocations)
        remaining = capped_shares - allocated

        for i in range(num_weeks):
            if remaining >= 100:
                allocations[i] += 100
                remaining -= 100
            else:
                break

        logger.debug(
            f"Allocations for {total_shares} shares across {num_weeks} weeks "
            f"({strategy.value}): {allocations}"
        )

        return allocations

    def adjust_sigma_for_week(self, week_number: int, base_sigma: Optional[float] = None) -> float:
        """
        Adjust sigma level based on week number.

        Week 1 (nearest): Slightly more aggressive (lower sigma)
            - Rationale: Shorter time to expiry, want more premium

        Week 2-3: Baseline sigma
            - Rationale: Standard positioning

        Week 4+: Slightly more conservative (higher sigma)
            - Rationale: More time for adverse moves, want more protection

        Args:
            week_number: Week index (1 = nearest)
            base_sigma: Base sigma level (default: config.base_sigma)

        Returns:
            Adjusted sigma level for the week
        """
        if base_sigma is None:
            base_sigma = self.config.base_sigma

        adjustment = self.config.sigma_adjustment_per_week

        if week_number == 1:
            # Near-term: slightly more aggressive (lower sigma = closer to ATM)
            return max(0.5, base_sigma - adjustment)
        elif week_number <= 3:
            # Mid-term: baseline
            return base_sigma
        else:
            # Far-term: slightly more conservative (higher sigma = further OTM)
            return base_sigma + adjustment

    def find_best_strike_for_sigma(
        self,
        options_chain: OptionsChain,
        expiration_date: str,
        target_sigma: float,
        current_price: float,
        volatility: float,
        option_type: str = "call",
    ) -> Optional[OptionContract]:
        """
        Find the best available strike near the target sigma level.

        Args:
            options_chain: Options chain to search
            expiration_date: Target expiration date
            target_sigma: Target sigma distance from current price
            current_price: Current stock price
            volatility: Annualized volatility
            option_type: "call" or "put"

        Returns:
            Best matching OptionContract, or None if none found
        """
        # Calculate DTE
        try:
            exp_date = date.fromisoformat(expiration_date)
            today = date.today()
            days_to_expiry = max(1, (exp_date - today).days)
        except ValueError:
            days_to_expiry = 7

        # Calculate target strike using sigma
        target_strike = self.optimizer.calculate_strike_at_sigma(
            current_price=current_price,
            volatility=volatility,
            days_to_expiry=days_to_expiry,
            sigma=target_sigma,
            option_type=option_type,
        ).theoretical_strike

        # Get contracts for this expiration
        if option_type == "call":
            contracts = [
                c for c in options_chain.get_calls() if c.expiration_date == expiration_date
            ]
        else:
            contracts = [
                c for c in options_chain.get_puts() if c.expiration_date == expiration_date
            ]

        if not contracts:
            return None

        # Filter to OTM contracts only
        if option_type == "call":
            contracts = [c for c in contracts if c.strike > current_price]
        else:
            contracts = [c for c in contracts if c.strike < current_price]

        if not contracts:
            return None

        # Find contract closest to target strike with valid bid
        valid_contracts = [c for c in contracts if c.bid and c.bid > 0]

        if not valid_contracts:
            # Fall back to any contract if none have bids
            valid_contracts = contracts

        # Sort by distance to target strike
        valid_contracts.sort(key=lambda c: abs(c.strike - target_strike))

        return valid_contracts[0] if valid_contracts else None

    def build_ladder(
        self,
        symbol: str,
        shares: int,
        current_price: float,
        volatility: float,
        options_chain: OptionsChain,
        option_type: str = "call",
        override_earnings_check: bool = False,
    ) -> LadderResult:
        """
        Build a complete ladder of covered positions.

        Args:
            symbol: Stock ticker symbol
            shares: Total shares available
            current_price: Current stock price
            volatility: Annualized volatility
            options_chain: Options chain for the symbol
            option_type: "call" for covered calls, "put" for cash-secured puts
            override_earnings_check: If True, don't skip earnings weeks

        Returns:
            LadderResult with complete ladder specification
        """
        symbol = symbol.upper()

        # Get weekly expirations
        expirations = self.get_weekly_expirations(options_chain)

        if not expirations:
            return LadderResult(
                symbol=symbol,
                option_type=option_type,
                current_price=current_price,
                volatility=volatility,
                total_shares=shares,
                shares_to_ladder=0,
                total_contracts=0,
                legs=[],
                total_gross_premium=0.0,
                total_net_premium=0.0,
                weighted_avg_delta=0.0,
                weighted_avg_dte=0.0,
                weighted_avg_yield_pct=0.0,
                warnings=["No weekly expirations found in options chain"],
                config_used=self.config,
            )

        # Get earnings dates
        earnings_dates = self.earnings_calendar.get_earnings_dates(symbol)

        # Filter out earnings weeks if configured
        valid_expirations = []
        skipped_for_earnings = []

        for exp_date in expirations:
            if self.config.skip_earnings_weeks and not override_earnings_check:
                spans_earnings, earn_date = self.earnings_calendar.expiration_spans_earnings(
                    symbol, exp_date
                )
                if spans_earnings:
                    skipped_for_earnings.append((exp_date, earn_date))
                    continue
            valid_expirations.append(exp_date)

        if not valid_expirations:
            return LadderResult(
                symbol=symbol,
                option_type=option_type,
                current_price=current_price,
                volatility=volatility,
                total_shares=shares,
                shares_to_ladder=0,
                total_contracts=0,
                legs=[],
                total_gross_premium=0.0,
                total_net_premium=0.0,
                weighted_avg_delta=0.0,
                weighted_avg_dte=0.0,
                weighted_avg_yield_pct=0.0,
                earnings_dates=earnings_dates,
                warnings=[f"All {len(expirations)} expirations span earnings dates"],
                config_used=self.config,
            )

        # Calculate allocations
        allocations = self.calculate_allocations(shares, len(valid_expirations))

        # Build each leg
        legs = []
        warnings = []

        for week_idx, (exp_date, shares_for_week) in enumerate(zip(valid_expirations, allocations)):
            week_number = week_idx + 1

            # Calculate DTE
            try:
                exp_date_obj = date.fromisoformat(exp_date)
                today = date.today()
                days_to_expiry = max(1, (exp_date_obj - today).days)
            except ValueError:
                days_to_expiry = 7 * week_number

            # Adjust sigma for week
            sigma = self.adjust_sigma_for_week(week_number)

            # Calculate contracts
            contracts = shares_for_week // 100

            # Create leg
            leg = LadderLeg(
                week_number=week_number,
                expiration_date=exp_date,
                days_to_expiry=days_to_expiry,
                strike=0.0,
                sigma_used=sigma,
                contracts=contracts,
                shares_covered=shares_for_week,
            )

            if contracts < self.config.min_contracts_per_leg:
                leg.is_actionable = False
                leg.rejection_reason = (
                    f"Contracts ({contracts}) < minimum ({self.config.min_contracts_per_leg})"
                )
                legs.append(leg)
                continue

            # Find best strike
            contract = self.find_best_strike_for_sigma(
                options_chain=options_chain,
                expiration_date=exp_date,
                target_sigma=sigma,
                current_price=current_price,
                volatility=volatility,
                option_type=option_type,
            )

            if contract is None:
                leg.is_actionable = False
                leg.rejection_reason = "No suitable contract found"
                legs.append(leg)
                continue

            # Populate leg with contract details
            leg.option_contract = contract
            leg.strike = contract.strike
            leg.bid = contract.bid or 0.0
            leg.ask = contract.ask or 0.0
            leg.mid_price = (leg.bid + leg.ask) / 2
            leg.gross_premium = leg.bid * 100 * contracts

            # Calculate delta and P(ITM)
            prob_result = self.optimizer.calculate_assignment_probability(
                strike=contract.strike,
                current_price=current_price,
                volatility=volatility,
                days_to_expiry=days_to_expiry,
                option_type=option_type,
            )
            leg.delta = abs(prob_result.delta)
            leg.p_itm = prob_result.probability

            # Check for warnings
            if leg.bid == 0:
                leg.warnings.append("Zero bid - may not be tradeable")
                leg.is_actionable = False
                leg.rejection_reason = "Zero bid price"

            spread_pct = ((leg.ask - leg.bid) / leg.mid_price * 100) if leg.mid_price > 0 else 100
            if spread_pct > 25:
                leg.warnings.append(f"Wide spread: {spread_pct:.1f}%")

            legs.append(leg)

        # Add warnings for skipped earnings weeks
        for exp_date, earn_date in skipped_for_earnings:
            warnings.append(f"Skipped {exp_date}: earnings on {earn_date}")

        # Calculate aggregate metrics
        actionable_legs = [leg for leg in legs if leg.is_actionable]

        total_contracts = sum(leg.contracts for leg in actionable_legs)
        total_gross_premium = sum(leg.gross_premium for leg in actionable_legs)
        shares_to_ladder = sum(leg.shares_covered for leg in actionable_legs)

        # Estimate net premium (rough estimate: gross - $0.65 per contract)
        estimated_commission = total_contracts * 0.65
        total_net_premium = total_gross_premium - estimated_commission

        # Weighted averages (weighted by contracts)
        if total_contracts > 0:
            weighted_avg_delta = (
                sum(leg.delta * leg.contracts for leg in actionable_legs) / total_contracts
            )

            weighted_avg_dte = (
                sum(leg.days_to_expiry * leg.contracts for leg in actionable_legs) / total_contracts
            )

            weighted_avg_yield = (
                sum(leg.annualized_yield_pct * leg.contracts for leg in actionable_legs)
                / total_contracts
            )
        else:
            weighted_avg_delta = 0.0
            weighted_avg_dte = 0.0
            weighted_avg_yield = 0.0

        result = LadderResult(
            symbol=symbol,
            option_type=option_type,
            current_price=current_price,
            volatility=volatility,
            total_shares=shares,
            shares_to_ladder=shares_to_ladder,
            total_contracts=total_contracts,
            legs=legs,
            total_gross_premium=total_gross_premium,
            total_net_premium=total_net_premium,
            weighted_avg_delta=weighted_avg_delta,
            weighted_avg_dte=weighted_avg_dte,
            weighted_avg_yield_pct=weighted_avg_yield,
            earnings_dates=earnings_dates,
            warnings=warnings,
            config_used=self.config,
        )

        logger.info(
            f"Built ladder for {symbol}: {total_contracts} contracts across "
            f"{len(actionable_legs)} weeks, ${total_gross_premium:.2f} gross premium"
        )

        return result

    def format_ladder_summary(self, result: LadderResult) -> str:
        """
        Format a human-readable summary of the ladder.

        Args:
            result: LadderResult to format

        Returns:
            Formatted string summary
        """
        lines = [
            f"=== Ladder Summary: {result.symbol} {result.option_type.upper()}S ===",
            f"Current Price: ${result.current_price:.2f}",
            f"Volatility: {result.volatility * 100:.1f}%",
            f"Total Shares: {result.total_shares} ({result.shares_to_ladder} in ladder)",
            f"Total Contracts: {result.total_contracts}",
            "",
            "--- Legs ---",
        ]

        for leg in result.legs:
            status = "✓" if leg.is_actionable else "✗"
            if leg.is_actionable:
                lines.append(
                    f"Week {leg.week_number} ({leg.expiration_date}, {leg.days_to_expiry}d): "
                    f"{status} {leg.contracts}x ${leg.strike:.2f} @ ${leg.bid:.2f} "
                    f"(δ={leg.delta:.3f}, σ={leg.sigma_used:.2f}) = ${leg.gross_premium:.2f}"
                )
            else:
                reason = leg.rejection_reason or "Not actionable"
                lines.append(
                    f"Week {leg.week_number} ({leg.expiration_date}, {leg.days_to_expiry}d): "
                    f"{status} {reason}"
                )

            for warning in leg.warnings:
                lines.append(f"    ⚠ {warning}")

        lines.extend(
            [
                "",
                "--- Summary ---",
                f"Total Gross Premium: ${result.total_gross_premium:.2f}",
                f"Total Net Premium (est): ${result.total_net_premium:.2f}",
                f"Weighted Avg Delta: {result.weighted_avg_delta:.4f}",
                f"Weighted Avg DTE: {result.weighted_avg_dte:.1f} days",
                f"Weighted Avg Yield: {result.weighted_avg_yield_pct:.2f}% annualized",
            ]
        )

        if result.warnings:
            lines.append("")
            lines.append("--- Warnings ---")
            for warning in result.warnings:
                lines.append(f"⚠ {warning}")

        return "\n".join(lines)
