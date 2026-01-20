"""Strike optimizer result dataclasses."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .base import OptionContract
    from .profiles import StrikeProfile


@dataclass
class StrikeResult:
    """
    Result of a strike calculation.

    Attributes:
        theoretical_strike: Exact calculated strike at N sigma
        tradeable_strike: Rounded to nearest available strike increment
        sigma: Number of standard deviations from current price
        current_price: Stock price used in calculation
        volatility: Annualized volatility used (as decimal)
        days_to_expiry: Days until option expiration
        option_type: "call" or "put"
        assignment_probability: Estimated probability of ITM at expiry
    """

    theoretical_strike: float
    tradeable_strike: float
    sigma: float
    current_price: float
    volatility: float
    days_to_expiry: int
    option_type: str
    assignment_probability: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "theoretical_strike": round(self.theoretical_strike, 4),
            "tradeable_strike": self.tradeable_strike,
            "sigma": self.sigma,
            "current_price": self.current_price,
            "volatility": round(self.volatility, 4),
            "volatility_pct": round(self.volatility * 100, 2),
            "days_to_expiry": self.days_to_expiry,
            "option_type": self.option_type,
            "assignment_probability": round(self.assignment_probability, 4)
            if self.assignment_probability
            else None,
            "assignment_probability_pct": round(self.assignment_probability * 100, 2)
            if self.assignment_probability
            else None,
        }


@dataclass
class ProbabilityResult:
    """
    Result of an assignment probability calculation.

    Attributes:
        probability: Probability of ITM at expiration (0-1)
        d1: Black-Scholes d1 parameter
        d2: Black-Scholes d2 parameter
        delta: Option delta (instantaneous probability proxy)
        strike: Strike price
        current_price: Current stock price
        volatility: Annualized volatility
        time_to_expiry: Time to expiration in years
        risk_free_rate: Risk-free interest rate used
        option_type: "call" or "put"
    """

    probability: float
    d1: float
    d2: float
    delta: float
    strike: float
    current_price: float
    volatility: float
    time_to_expiry: float
    risk_free_rate: float
    option_type: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "probability": round(self.probability, 4),
            "probability_pct": round(self.probability * 100, 2),
            "d1": round(self.d1, 4),
            "d2": round(self.d2, 4),
            "delta": round(self.delta, 4),
            "strike": self.strike,
            "current_price": self.current_price,
            "volatility": round(self.volatility, 4),
            "time_to_expiry_years": round(self.time_to_expiry, 4),
            "risk_free_rate": round(self.risk_free_rate, 4),
            "option_type": self.option_type,
        }


@dataclass
class StrikeRecommendation:
    """
    A recommended strike with full analysis.

    Attributes:
        contract: The option contract (if available from chain)
        strike: Strike price
        expiration_date: Expiration date (YYYY-MM-DD)
        option_type: "call" or "put"
        sigma_distance: Distance from current price in sigmas
        assignment_probability: Probability of ITM at expiry
        bid: Bid price (premium receivable)
        ask: Ask price
        mid_price: Mid-point of bid/ask
        bid_ask_spread_pct: Spread as percentage of mid price
        open_interest: Open interest
        volume: Daily volume
        implied_volatility: Market IV for this strike
        profile: StrikeProfile this recommendation fits
        warnings: List of warning messages
    """

    contract: Optional["OptionContract"]
    strike: float
    expiration_date: str
    option_type: str
    sigma_distance: float
    assignment_probability: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    mid_price: Optional[float] = None
    bid_ask_spread_pct: Optional[float] = None
    open_interest: Optional[int] = None
    volume: Optional[int] = None
    implied_volatility: Optional[float] = None
    profile: Optional["StrikeProfile"] = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "strike": self.strike,
            "expiration_date": self.expiration_date,
            "option_type": self.option_type,
            "sigma_distance": round(self.sigma_distance, 2),
            "assignment_probability_pct": round(self.assignment_probability * 100, 2),
            "bid": self.bid,
            "ask": self.ask,
            "mid_price": round(self.mid_price, 4) if self.mid_price else None,
            "bid_ask_spread_pct": round(self.bid_ask_spread_pct, 2)
            if self.bid_ask_spread_pct
            else None,
            "open_interest": self.open_interest,
            "volume": self.volume,
            "implied_volatility_pct": round(self.implied_volatility * 100, 2)
            if self.implied_volatility
            else None,
            "profile": self.profile.value if self.profile else None,
            "warnings": self.warnings,
        }


@dataclass
class ProfileStrikesResult:
    """
    Result of calculating strikes for all risk profiles.

    Contains the strikes for each profile plus any warnings about
    issues like strike collisions or short DTE.

    Attributes:
        strikes: Dictionary mapping each StrikeProfile to its StrikeResult
        warnings: List of warning messages about the calculation
        collapsed_profiles: List of profile pairs that map to the same tradeable strike
        is_short_dte: Whether DTE is considered short (<14 days)
    """

    strikes: dict["StrikeProfile", "StrikeResult"]
    warnings: list[str] = field(default_factory=list)
    collapsed_profiles: list[tuple] = field(default_factory=list)
    is_short_dte: bool = False

    def __getitem__(self, profile: "StrikeProfile") -> "StrikeResult":
        """Allow dict-like access for backward compatibility."""
        return self.strikes[profile]

    def __iter__(self):
        """Allow iteration over profiles."""
        return iter(self.strikes)

    def items(self):
        """Allow dict-like items() for backward compatibility."""
        return self.strikes.items()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "strikes": {p.value: r.to_dict() for p, r in self.strikes.items()},
            "warnings": self.warnings,
            "collapsed_profiles": [(p1.value, p2.value) for p1, p2 in self.collapsed_profiles],
            "is_short_dte": self.is_short_dte,
        }
