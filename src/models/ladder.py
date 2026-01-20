"""Ladder builder dataclasses."""

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .base import OptionContract
    from .profiles import StrikeProfile


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
ALLOCATION_WEIGHTS: dict[AllocationStrategy, list[int]] = {
    AllocationStrategy.FRONT_WEIGHTED: [4, 3, 2, 1],  # Near-term gets more
    AllocationStrategy.BACK_WEIGHTED: [1, 2, 3, 4],  # Far-term gets more
}


@dataclass
class LadderConfig:
    """
    Configuration for ladder building.

    Attributes:
        allocation_strategy: How to allocate shares across weeks
        weeks_to_ladder: Number of weekly expirations to include (default 4)
        base_sigma: Base sigma level for strike selection (default 1.5)
        sigma_adjustment_per_week: Sigma adjustment per week from baseline
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
    strike_profile: "StrikeProfile" = None  # Set in __post_init__

    def __post_init__(self) -> None:
        """Validate configuration."""
        # Import here to avoid circular imports
        from .profiles import StrikeProfile

        if self.strike_profile is None:
            self.strike_profile = StrikeProfile.CONSERVATIVE

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
        shares_covered: Number of shares covered (contracts x 100)
        option_contract: Selected option contract (if available)
        bid: Bid price of the option
        ask: Ask price of the option
        mid_price: Mid-point of bid/ask
        gross_premium: Expected premium (bid x 100 x contracts)
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
    option_contract: Optional["OptionContract"] = None
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
