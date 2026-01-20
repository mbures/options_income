"""Overlay scanner dataclasses."""

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .base import OptionContract
    from .profiles import DeltaBand


class SlippageModel(Enum):
    """
    Slippage models for execution cost estimation.

    Slippage represents the difference between expected fill price
    and actual fill price.
    """

    HALF_SPREAD = "half_spread"  # Assume fill at mid
    HALF_SPREAD_CAPPED = "half_spread_capped"  # Half spread, capped at max
    FULL_SPREAD = "full_spread"  # Assume fill at bid (worst case)
    NONE = "none"  # No slippage (optimistic)


class RejectionReason(Enum):
    """
    Reasons for rejecting a strike from recommendations.

    Explicit rejection reasons help users understand why certain
    strikes were excluded from the top recommendations.
    """

    ZERO_BID = "zero_bid"
    LOW_PREMIUM = "low_premium"
    WIDE_SPREAD_ABSOLUTE = "wide_spread_absolute"
    WIDE_SPREAD_RELATIVE = "wide_spread_relative"
    LOW_OPEN_INTEREST = "low_open_interest"
    LOW_VOLUME = "low_volume"
    EARNINGS_WEEK = "earnings_week"
    OUTSIDE_DELTA_BAND = "outside_delta_band"
    INSUFFICIENT_SHARES = "insufficient_shares"
    ITM_STRIKE = "itm_strike"
    NET_CREDIT_TOO_LOW = "net_credit_too_low"  # Deprecated: use YIELD_TOO_LOW
    YIELD_TOO_LOW = "yield_too_low"  # net_credit / notional < min_weekly_yield_bps
    FRICTION_TOO_HIGH = "friction_too_high"  # net_credit < min_friction_multiple * costs
    EARLY_EXERCISE_RISK = "early_exercise_risk"


@dataclass
class RejectionDetail:
    """
    Detailed rejection information with margin tracking.

    Tracks not just why a candidate was rejected, but how close it was
    to passing each constraint. This enables near-miss analysis.

    Attributes:
        reason: The rejection reason enum
        actual_value: The candidate's actual value for this constraint
        threshold: The threshold that needed to be met
        margin: How far from passing (normalized 0-1, 0 = at threshold)
        margin_display: Human-readable margin description
    """

    reason: RejectionReason
    actual_value: float
    threshold: float
    margin: float  # 0 = at threshold, 1 = far from threshold
    margin_display: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "reason": self.reason.value,
            "actual_value": round(self.actual_value, 4),
            "threshold": round(self.threshold, 4),
            "margin": round(self.margin, 4),
            "margin_display": self.margin_display,
        }


@dataclass
class PortfolioHolding:
    """
    Represents a single portfolio holding.

    Attributes:
        symbol: Stock ticker symbol (required)
        shares: Number of shares held (required, must be non-negative)
        cost_basis: Average cost per share (optional, for tax analytics)
        acquired_date: Date shares were acquired (optional, for holding period)
        account_type: 'taxable' or 'qualified' (optional, affects warnings)
    """

    symbol: str
    shares: int
    cost_basis: Optional[float] = None
    acquired_date: Optional[str] = None  # ISO format YYYY-MM-DD
    account_type: Optional[str] = None  # 'taxable' or 'qualified'

    def __post_init__(self) -> None:
        """Validate holding data."""
        self.symbol = self.symbol.upper().strip()
        if not self.symbol or not self.symbol.isalnum():
            raise ValueError(f"Invalid symbol: {self.symbol}")
        if self.shares < 0:
            raise ValueError(f"Shares must be non-negative, got {self.shares}")
        if self.cost_basis is not None and self.cost_basis < 0:
            raise ValueError(f"Cost basis must be non-negative, got {self.cost_basis}")
        if self.account_type and self.account_type not in ("taxable", "qualified"):
            raise ValueError(
                f"Account type must be 'taxable' or 'qualified', got {self.account_type}"
            )


@dataclass
class ScannerConfig:
    """
    Configuration for the overlay scanner.

    Attributes:
        overwrite_cap_pct: Max percentage of shares to overwrite (default 25%)
        per_contract_fee: Broker fee per contract (default $0.65)
        slippage_model: How to estimate fill price (default: half_spread_capped)
        max_slippage_per_contract: Cap on slippage estimate (default $0.10/share)
        min_weekly_yield_bps: Minimum yield in basis points per week (default 10 bps).
        min_friction_multiple: Net credit must be >= this multiple of friction costs
        skip_earnings_default: Exclude earnings-week expirations (default True)
        delta_band: Target delta band for selection (default CONSERVATIVE)
        min_open_interest: Minimum OI for tradability (default 100)
        min_volume: Minimum daily volume (default 10)
        max_spread_absolute: Maximum bid-ask spread in dollars (default $0.10)
        max_spread_relative_pct: Maximum spread as % of mid (default 20%)
        min_mid_for_relative_spread: Minimum mid price before relative spread filter
        min_bid_price: Minimum bid price to consider (default $0.05)
        weeks_to_scan: Number of weekly expirations to scan (default 3)
        risk_free_rate: Risk-free rate for calculations (default 0.05)
    """

    overwrite_cap_pct: float = 25.0
    per_contract_fee: float = 0.65
    slippage_model: SlippageModel = SlippageModel.HALF_SPREAD_CAPPED
    max_slippage_per_contract: float = 0.10
    min_weekly_yield_bps: float = 10.0
    min_friction_multiple: float = 2.0
    skip_earnings_default: bool = True
    delta_band: "DeltaBand" = None  # Set in __post_init__
    min_open_interest: int = 100
    min_volume: int = 10
    max_spread_absolute: float = 0.10
    max_spread_relative_pct: float = 20.0
    min_mid_for_relative_spread: float = 0.50
    min_bid_price: float = 0.05
    weeks_to_scan: int = 3
    risk_free_rate: float = 0.05

    def __post_init__(self) -> None:
        """Validate configuration."""
        # Import here to avoid circular imports
        from .profiles import DeltaBand

        if self.delta_band is None:
            self.delta_band = DeltaBand.CONSERVATIVE

        if not 0 < self.overwrite_cap_pct <= 100:
            raise ValueError(
                f"overwrite_cap_pct must be between 0 and 100, got {self.overwrite_cap_pct}"
            )
        if self.per_contract_fee < 0:
            raise ValueError(f"per_contract_fee must be non-negative, got {self.per_contract_fee}")
        if self.min_weekly_yield_bps < 0:
            raise ValueError(
                f"min_weekly_yield_bps must be non-negative, got {self.min_weekly_yield_bps}"
            )
        if self.min_friction_multiple < 1:
            raise ValueError(
                f"min_friction_multiple must be >= 1, got {self.min_friction_multiple}"
            )


@dataclass
class ExecutionCostEstimate:
    """
    Estimated execution costs for a trade.

    Attributes:
        gross_premium: Bid price x 100 (premium before costs)
        commission: Broker fee per contract
        slippage: Estimated slippage cost
        net_credit: Gross premium - commission - slippage
        net_credit_per_share: Net credit / 100
    """

    gross_premium: float
    commission: float
    slippage: float
    net_credit: float
    net_credit_per_share: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "gross_premium": round(self.gross_premium, 2),
            "commission": round(self.commission, 2),
            "slippage": round(self.slippage, 2),
            "net_credit": round(self.net_credit, 2),
            "net_credit_per_share": round(self.net_credit_per_share, 4),
        }


@dataclass
class CandidateStrike:
    """
    A candidate strike for covered call overlay.

    Attributes:
        contract: The option contract
        strike: Strike price
        expiration_date: Expiration date (YYYY-MM-DD)
        delta: Option delta (computed via Black-Scholes)
        p_itm: Probability of ITM at expiration
        sigma_distance: Distance from current price in sigmas (diagnostic)
        bid: Bid price
        ask: Ask price
        mid_price: Mid-point of bid/ask
        spread_absolute: Bid-ask spread in dollars
        spread_relative_pct: Spread as % of mid
        open_interest: Open interest
        volume: Daily volume
        cost_estimate: Execution cost estimate
        delta_band: Which delta band this strike falls into
        contracts_to_sell: Number of contracts based on overwrite cap
        total_net_credit: Net credit for all contracts
        annualized_yield_pct: Simple annualized yield (net credit / position value)
        days_to_expiry: Days until expiration
        warnings: List of warning messages
        rejection_reasons: List of rejection reasons (if filtered out)
        rejection_details: Detailed rejection info
        binding_constraint: The constraint that caused rejection
        near_miss_score: Score for near-miss analysis
        is_recommended: Whether this strike passed all filters
    """

    contract: "OptionContract"
    strike: float
    expiration_date: str
    delta: float
    p_itm: float
    sigma_distance: Optional[float]
    bid: float
    ask: float
    mid_price: float
    spread_absolute: float
    spread_relative_pct: float
    open_interest: int
    volume: int
    cost_estimate: ExecutionCostEstimate
    delta_band: Optional["DeltaBand"]
    contracts_to_sell: int
    total_net_credit: float
    annualized_yield_pct: float
    days_to_expiry: int
    warnings: list[str] = field(default_factory=list)
    rejection_reasons: list[RejectionReason] = field(default_factory=list)
    rejection_details: list["RejectionDetail"] = field(default_factory=list)
    binding_constraint: Optional["RejectionDetail"] = None
    near_miss_score: float = 0.0
    is_recommended: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "strike": self.strike,
            "expiration_date": self.expiration_date,
            "delta": round(self.delta, 4),
            "p_itm_pct": round(self.p_itm * 100, 2),
            "sigma_distance": round(self.sigma_distance, 2) if self.sigma_distance else None,
            "bid": round(self.bid, 2),
            "ask": round(self.ask, 2),
            "mid_price": round(self.mid_price, 2),
            "spread_absolute": round(self.spread_absolute, 2),
            "spread_relative_pct": round(self.spread_relative_pct, 2),
            "open_interest": self.open_interest,
            "volume": self.volume,
            "cost_estimate": self.cost_estimate.to_dict(),
            "delta_band": self.delta_band.value if self.delta_band else None,
            "contracts_to_sell": self.contracts_to_sell,
            "total_net_credit": round(self.total_net_credit, 2),
            "annualized_yield_pct": round(self.annualized_yield_pct, 2),
            "days_to_expiry": self.days_to_expiry,
            "warnings": self.warnings,
            "rejection_reasons": [r.value for r in self.rejection_reasons],
            "rejection_details": [d.to_dict() for d in self.rejection_details],
            "binding_constraint": self.binding_constraint.to_dict()
            if self.binding_constraint
            else None,
            "near_miss_score": round(self.near_miss_score, 4),
            "is_recommended": self.is_recommended,
        }


@dataclass
class BrokerChecklist:
    """
    Per-trade broker checklist for verification before execution.

    Attributes:
        symbol: Stock symbol
        action: Trade action (e.g., "SELL TO OPEN")
        contracts: Number of contracts
        strike: Strike price
        expiration: Expiration date
        option_type: "CALL" or "PUT"
        limit_price: Suggested limit price (mid or slightly below)
        min_acceptable_credit: Minimum credit to accept (bid)
        checks: List of verification items
        warnings: List of warnings to review
    """

    symbol: str
    action: str
    contracts: int
    strike: float
    expiration: str
    option_type: str
    limit_price: float
    min_acceptable_credit: float
    checks: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "symbol": self.symbol,
            "action": self.action,
            "contracts": self.contracts,
            "strike": self.strike,
            "expiration": self.expiration,
            "option_type": self.option_type,
            "limit_price": round(self.limit_price, 2),
            "min_acceptable_credit": round(self.min_acceptable_credit, 2),
            "checks": self.checks,
            "warnings": self.warnings,
        }


@dataclass
class LLMMemoPayload:
    """
    Structured JSON payload for optional LLM decision memo generation.

    Attributes:
        symbol: Stock symbol
        current_price: Current stock price
        shares_held: Total shares in portfolio
        contracts_to_write: Number of contracts to sell
        candidate: The recommended strike candidate
        holding: Portfolio holding info
        risk_profile: Delta band used
        earnings_status: Whether earnings are clear
        dividend_status: Dividend verification status
        account_type: Taxable vs qualified
        timestamp: When this memo was generated
    """

    symbol: str
    current_price: float
    shares_held: int
    contracts_to_write: int
    candidate: dict[str, Any]
    holding: dict[str, Any]
    risk_profile: str
    earnings_status: str
    dividend_status: str
    account_type: Optional[str]
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "symbol": self.symbol,
            "current_price": round(self.current_price, 2),
            "shares_held": self.shares_held,
            "contracts_to_write": self.contracts_to_write,
            "candidate": self.candidate,
            "holding": self.holding,
            "risk_profile": self.risk_profile,
            "earnings_status": self.earnings_status,
            "dividend_status": self.dividend_status,
            "account_type": self.account_type,
            "timestamp": self.timestamp,
        }


@dataclass
class ScanResult:
    """
    Result of scanning a single holding.

    Attributes:
        symbol: Stock symbol
        current_price: Current stock price
        shares_held: Total shares held
        contracts_available: Max contracts based on overwrite cap
        recommended_strikes: List of recommended strikes (passed all filters)
        rejected_strikes: List of rejected strikes with reasons
        near_miss_candidates: Top 5 rejected candidates by near-miss score
        earnings_dates: Earnings dates found
        has_earnings_conflict: Whether any expiration spans earnings
        broker_checklist: Checklist for the top recommendation
        llm_memo_payload: Payload for LLM memo generation
        warnings: General warnings
        error: Error message if scan failed
    """

    symbol: str
    current_price: float
    shares_held: int
    contracts_available: int
    recommended_strikes: list[CandidateStrike] = field(default_factory=list)
    rejected_strikes: list[CandidateStrike] = field(default_factory=list)
    near_miss_candidates: list[CandidateStrike] = field(default_factory=list)
    earnings_dates: list[str] = field(default_factory=list)
    has_earnings_conflict: bool = False
    broker_checklist: Optional[BrokerChecklist] = None
    llm_memo_payload: Optional[LLMMemoPayload] = None
    warnings: list[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "symbol": self.symbol,
            "current_price": round(self.current_price, 2),
            "shares_held": self.shares_held,
            "contracts_available": self.contracts_available,
            "recommended_strikes": [s.to_dict() for s in self.recommended_strikes],
            "rejected_strikes": [s.to_dict() for s in self.rejected_strikes],
            "near_miss_candidates": [s.to_dict() for s in self.near_miss_candidates],
            "earnings_dates": self.earnings_dates,
            "has_earnings_conflict": self.has_earnings_conflict,
            "broker_checklist": self.broker_checklist.to_dict() if self.broker_checklist else None,
            "llm_memo_payload": self.llm_memo_payload.to_dict() if self.llm_memo_payload else None,
            "warnings": self.warnings,
            "error": self.error,
        }
