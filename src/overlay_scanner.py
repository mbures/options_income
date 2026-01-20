"""
Weekly Overlay Scanner for covered call strategies.

This module provides a holdings-driven scanner for generating weekly covered
call recommendations with:
- Portfolio holdings input with overwrite cap sizing (FR-42, FR-43)
- Earnings week exclusion as hard gate (FR-45)
- Execution cost model with fees and slippage (FR-44)
- Delta-band risk profiles for weekly selection (FR-47)
- Tradability filters (FR-49)
- Broker checklist and LLM memo payload output (FR-50)

The scanner is designed for a broker-first workflow where the system generates
recommendations and the user executes trades manually at their broker.

Example:
    from src.overlay_scanner import OverlayScanner, PortfolioHolding, ScannerConfig

    holdings = [
        PortfolioHolding(symbol="AAPL", shares=500),
        PortfolioHolding(symbol="MSFT", shares=300),
    ]

    scanner = OverlayScanner(
        finnhub_client=finnhub_client,
        strike_optimizer=optimizer,
        config=ScannerConfig()
    )

    results = scanner.scan_portfolio(holdings, current_prices)
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple

from .models import OptionContract, OptionsChain
from .strike_optimizer import StrikeOptimizer, ProbabilityResult

logger = logging.getLogger(__name__)


# =============================================================================
# Data Models
# =============================================================================


class DeltaBand(Enum):
    """
    Delta-band risk profiles for weekly covered call selection.

    Delta bands are the PRIMARY selector for weekly covered calls as they
    provide a direct measure of ITM probability/risk. Lower delta = lower
    assignment probability.

    These bands are calibrated for weekly options (5-14 DTE).
    """
    DEFENSIVE = "defensive"       # 0.05-0.10 delta, ~5-10% P(ITM)
    CONSERVATIVE = "conservative" # 0.10-0.15 delta, ~10-15% P(ITM)
    MODERATE = "moderate"         # 0.15-0.25 delta, ~15-25% P(ITM)
    AGGRESSIVE = "aggressive"     # 0.25-0.35 delta, ~25-35% P(ITM)


# Delta ranges for each band (min_delta, max_delta)
DELTA_BAND_RANGES: Dict[DeltaBand, Tuple[float, float]] = {
    DeltaBand.DEFENSIVE: (0.05, 0.10),
    DeltaBand.CONSERVATIVE: (0.10, 0.15),
    DeltaBand.MODERATE: (0.15, 0.25),
    DeltaBand.AGGRESSIVE: (0.25, 0.35),
}


class SlippageModel(Enum):
    """
    Slippage models for execution cost estimation.

    Slippage represents the difference between expected fill price
    and actual fill price.
    """
    HALF_SPREAD = "half_spread"           # Assume fill at mid
    HALF_SPREAD_CAPPED = "half_spread_capped"  # Half spread, capped at max
    FULL_SPREAD = "full_spread"           # Assume fill at bid (worst case)
    NONE = "none"                         # No slippage (optimistic)


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
    NET_CREDIT_TOO_LOW = "net_credit_too_low"
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

    def to_dict(self) -> Dict[str, Any]:
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
    account_type: Optional[str] = None   # 'taxable' or 'qualified'

    def __post_init__(self) -> None:
        """Validate holding data."""
        self.symbol = self.symbol.upper().strip()
        if not self.symbol or not self.symbol.isalnum():
            raise ValueError(f"Invalid symbol: {self.symbol}")
        if self.shares < 0:
            raise ValueError(f"Shares must be non-negative, got {self.shares}")
        if self.cost_basis is not None and self.cost_basis < 0:
            raise ValueError(f"Cost basis must be non-negative, got {self.cost_basis}")
        if self.account_type and self.account_type not in ('taxable', 'qualified'):
            raise ValueError(f"Account type must be 'taxable' or 'qualified', got {self.account_type}")


@dataclass
class ScannerConfig:
    """
    Configuration for the overlay scanner.

    Attributes:
        overwrite_cap_pct: Max percentage of shares to overwrite (default 25%)
        per_contract_fee: Broker fee per contract (default $0.65)
        slippage_model: How to estimate fill price (default: half_spread_capped)
        max_slippage_per_contract: Cap on slippage estimate (default $0.10/share)
        min_net_credit: Minimum net credit per contract to recommend
        skip_earnings_default: Exclude earnings-week expirations (default True)
        delta_band: Target delta band for selection (default CONSERVATIVE)
        min_open_interest: Minimum OI for tradability (default 100)
        min_volume: Minimum daily volume (default 10)
        max_spread_absolute: Maximum bid-ask spread in dollars (default $0.20)
        max_spread_relative_pct: Maximum spread as % of mid (default 15%)
        min_bid_price: Minimum bid price to consider (default $0.05)
        weeks_to_scan: Number of weekly expirations to scan (default 3)
    """
    overwrite_cap_pct: float = 25.0
    per_contract_fee: float = 0.65
    slippage_model: SlippageModel = SlippageModel.HALF_SPREAD_CAPPED
    max_slippage_per_contract: float = 0.10  # $0.10 per share = $10 per contract
    min_net_credit: float = 5.00  # Minimum $5 net credit per contract
    skip_earnings_default: bool = True
    delta_band: DeltaBand = DeltaBand.CONSERVATIVE
    min_open_interest: int = 100
    min_volume: int = 10
    max_spread_absolute: float = 0.20
    max_spread_relative_pct: float = 15.0
    min_bid_price: float = 0.05
    weeks_to_scan: int = 3
    risk_free_rate: float = 0.05

    def __post_init__(self) -> None:
        """Validate configuration."""
        if not 0 < self.overwrite_cap_pct <= 100:
            raise ValueError(f"overwrite_cap_pct must be between 0 and 100, got {self.overwrite_cap_pct}")
        if self.per_contract_fee < 0:
            raise ValueError(f"per_contract_fee must be non-negative, got {self.per_contract_fee}")
        if self.min_net_credit < 0:
            raise ValueError(f"min_net_credit must be non-negative, got {self.min_net_credit}")


@dataclass
class ExecutionCostEstimate:
    """
    Estimated execution costs for a trade.

    Attributes:
        gross_premium: Bid price × 100 (premium before costs)
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

    def to_dict(self) -> Dict[str, Any]:
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
        is_recommended: Whether this strike passed all filters
    """
    contract: OptionContract
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
    delta_band: Optional[DeltaBand]
    contracts_to_sell: int
    total_net_credit: float
    annualized_yield_pct: float
    days_to_expiry: int
    warnings: List[str] = field(default_factory=list)
    rejection_reasons: List[RejectionReason] = field(default_factory=list)
    rejection_details: List["RejectionDetail"] = field(default_factory=list)
    binding_constraint: Optional["RejectionDetail"] = None
    near_miss_score: float = 0.0
    is_recommended: bool = True

    def to_dict(self) -> Dict[str, Any]:
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
            "binding_constraint": self.binding_constraint.to_dict() if self.binding_constraint else None,
            "near_miss_score": round(self.near_miss_score, 4),
            "is_recommended": self.is_recommended,
        }


@dataclass
class BrokerChecklist:
    """
    Per-trade broker checklist for verification before execution.

    This checklist should be reviewed at the broker before placing the trade.

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
    checks: List[str]
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
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

    This payload contains all relevant data for an LLM to generate
    a human-readable decision memo explaining the trade rationale.

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
    candidate: Dict[str, Any]
    holding: Dict[str, Any]
    risk_profile: str
    earnings_status: str
    dividend_status: str
    account_type: Optional[str]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
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
    recommended_strikes: List[CandidateStrike] = field(default_factory=list)
    rejected_strikes: List[CandidateStrike] = field(default_factory=list)
    near_miss_candidates: List[CandidateStrike] = field(default_factory=list)
    earnings_dates: List[str] = field(default_factory=list)
    has_earnings_conflict: bool = False
    broker_checklist: Optional[BrokerChecklist] = None
    llm_memo_payload: Optional[LLMMemoPayload] = None
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
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


# =============================================================================
# Earnings Calendar Cache
# =============================================================================


class EarningsCalendar:
    """
    Cached earnings calendar for earnings week exclusion.

    Fetches and caches earnings dates from Finnhub for efficient
    repeated lookups.
    """

    def __init__(self, finnhub_client: Any, cache_ttl_hours: int = 24):
        """
        Initialize earnings calendar.

        Args:
            finnhub_client: FinnhubClient instance for API calls
            cache_ttl_hours: Cache time-to-live in hours (default 24)
        """
        self._client = finnhub_client
        self._cache: Dict[str, Tuple[List[str], float]] = {}
        self._cache_ttl = cache_ttl_hours * 3600

    def get_earnings_dates(
        self,
        symbol: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> List[str]:
        """
        Get earnings dates for a symbol within date range.

        Args:
            symbol: Stock ticker symbol
            from_date: Start date (YYYY-MM-DD), default today
            to_date: End date (YYYY-MM-DD), default +60 days

        Returns:
            List of earnings dates (YYYY-MM-DD format)
        """
        symbol = symbol.upper()

        # Check cache
        cache_key = symbol
        if cache_key in self._cache:
            dates, cached_at = self._cache[cache_key]
            if (datetime.now().timestamp() - cached_at) < self._cache_ttl:
                logger.debug(f"Cache hit for {symbol} earnings dates")
                return dates

        # Set default date range
        now = datetime.now()
        if from_date is None:
            from_date = now.strftime("%Y-%m-%d")
        if to_date is None:
            to_date = (now + timedelta(days=60)).strftime("%Y-%m-%d")

        # Fetch from Finnhub
        try:
            earnings_dates = self._fetch_earnings_from_finnhub(symbol, from_date, to_date)
            # Cache the results
            self._cache[cache_key] = (earnings_dates, datetime.now().timestamp())
            logger.info(f"Fetched {len(earnings_dates)} earnings dates for {symbol}")
            return earnings_dates
        except Exception as e:
            logger.warning(f"Failed to fetch earnings for {symbol}: {e}")
            return []

    def _fetch_earnings_from_finnhub(
        self,
        symbol: str,
        from_date: str,
        to_date: str
    ) -> List[str]:
        """
        Fetch earnings dates from Finnhub API via FinnhubClient.

        Args:
            symbol: Stock ticker symbol
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)

        Returns:
            List of earnings dates (YYYY-MM-DD format)
        """
        return self._client.get_earnings_calendar(symbol, from_date, to_date)

    def expiration_spans_earnings(
        self,
        symbol: str,
        expiration_date: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if an expiration date spans an earnings announcement.

        Args:
            symbol: Stock ticker symbol
            expiration_date: Option expiration date (YYYY-MM-DD)

        Returns:
            Tuple of (spans_earnings: bool, earnings_date: str or None)
        """
        now = datetime.now()
        try:
            exp_dt = datetime.fromisoformat(expiration_date)
        except ValueError:
            return False, None

        earnings_dates = self.get_earnings_dates(symbol)

        for earn_date in earnings_dates:
            try:
                earn_dt = datetime.fromisoformat(earn_date)
                if now <= earn_dt <= exp_dt:
                    return True, earn_date
            except ValueError:
                continue

        return False, None

    def clear_cache(self, symbol: Optional[str] = None) -> None:
        """Clear cache for symbol or all symbols."""
        if symbol:
            self._cache.pop(symbol.upper(), None)
        else:
            self._cache.clear()


# =============================================================================
# Overlay Scanner
# =============================================================================


class OverlayScanner:
    """
    Weekly covered call overlay scanner.

    Scans portfolio holdings and generates ranked covered call recommendations
    with a broker-first workflow.

    Features:
    - Holdings-driven scanning with overwrite cap sizing
    - Delta-band primary selection for weekly calls
    - Earnings-week exclusion by default (hard gate)
    - Net-credit ranking using execution cost model
    - Tradability filters with explicit rejection reasons
    - Broker checklist and LLM memo payload generation

    Example:
        scanner = OverlayScanner(
            finnhub_client=client,
            strike_optimizer=optimizer,
            config=ScannerConfig()
        )

        holdings = [PortfolioHolding("AAPL", 500)]
        prices = {"AAPL": 185.50}

        results = scanner.scan_portfolio(holdings, prices, options_chains)
    """

    def __init__(
        self,
        finnhub_client: Any,
        strike_optimizer: StrikeOptimizer,
        config: Optional[ScannerConfig] = None
    ):
        """
        Initialize the overlay scanner.

        Args:
            finnhub_client: FinnhubClient instance for API calls
            strike_optimizer: StrikeOptimizer for probability calculations
            config: Scanner configuration (uses defaults if None)
        """
        self.finnhub_client = finnhub_client
        self.optimizer = strike_optimizer
        self.config = config or ScannerConfig()
        self.earnings_calendar = EarningsCalendar(finnhub_client)

        logger.info(f"OverlayScanner initialized with config: "
                   f"delta_band={self.config.delta_band.value}, "
                   f"overwrite_cap={self.config.overwrite_cap_pct}%")

    def calculate_contracts_to_sell(self, shares: int) -> int:
        """
        Calculate number of contracts to sell based on overwrite cap.

        Formula: floor(shares × overwrite_cap_pct / 100 / 100)

        If result is 0, the holding is non-actionable.

        Args:
            shares: Number of shares held

        Returns:
            Number of contracts to sell (may be 0)
        """
        if shares < 100:
            return 0

        contracts = int(shares * self.config.overwrite_cap_pct / 100 / 100)
        return max(0, contracts)

    def calculate_execution_cost(
        self,
        bid: float,
        ask: float,
        contracts: int = 1
    ) -> ExecutionCostEstimate:
        """
        Calculate estimated execution costs for a trade.

        Args:
            bid: Bid price per share
            ask: Ask price per share
            contracts: Number of contracts (default 1)

        Returns:
            ExecutionCostEstimate with all cost components
        """
        gross_premium = bid * 100 * contracts
        commission = self.config.per_contract_fee * contracts

        # Calculate slippage based on model
        spread = ask - bid
        if self.config.slippage_model == SlippageModel.NONE:
            slippage_per_share = 0
        elif self.config.slippage_model == SlippageModel.FULL_SPREAD:
            slippage_per_share = 0  # Already using bid price
        elif self.config.slippage_model == SlippageModel.HALF_SPREAD:
            slippage_per_share = spread / 2
        else:  # HALF_SPREAD_CAPPED
            slippage_per_share = min(spread / 2, self.config.max_slippage_per_contract)

        slippage = slippage_per_share * 100 * contracts
        net_credit = gross_premium - commission - slippage
        net_credit_per_share = net_credit / (100 * contracts) if contracts > 0 else 0

        return ExecutionCostEstimate(
            gross_premium=gross_premium,
            commission=commission,
            slippage=slippage,
            net_credit=net_credit,
            net_credit_per_share=net_credit_per_share
        )

    def compute_delta(
        self,
        strike: float,
        current_price: float,
        volatility: float,
        days_to_expiry: int,
        option_type: str = "call"
    ) -> Tuple[float, float]:
        """
        Compute Black-Scholes delta and P(ITM) for a strike.

        Args:
            strike: Strike price
            current_price: Current stock price
            volatility: Annualized volatility as decimal
            days_to_expiry: Days until expiration
            option_type: "call" or "put"

        Returns:
            Tuple of (delta, p_itm)
        """
        prob_result = self.optimizer.calculate_assignment_probability(
            strike=strike,
            current_price=current_price,
            volatility=volatility,
            days_to_expiry=max(1, days_to_expiry),
            option_type=option_type
        )
        return abs(prob_result.delta), prob_result.probability

    def get_delta_band(self, delta: float) -> Optional[DeltaBand]:
        """
        Determine which delta band a given delta falls into.

        Args:
            delta: Option delta (absolute value)

        Returns:
            DeltaBand or None if outside all bands
        """
        delta = abs(delta)
        for band, (min_d, max_d) in DELTA_BAND_RANGES.items():
            if min_d <= delta < max_d:
                return band
        return None

    def _calculate_margin(
        self,
        actual: float,
        threshold: float,
        constraint_type: str
    ) -> Tuple[float, str]:
        """
        Calculate normalized margin from threshold.

        Args:
            actual: Actual value
            threshold: Threshold value
            constraint_type: 'min' (actual must be >= threshold) or 'max' (actual must be <= threshold)

        Returns:
            Tuple of (margin, display_string)
            margin: 0 = at threshold, higher = further from passing
        """
        if constraint_type == 'min':
            # For minimum constraints: need actual >= threshold
            if threshold == 0:
                margin = 1.0 if actual <= 0 else 0.0
            else:
                gap = threshold - actual
                margin = max(0, gap / threshold)
            shortfall = threshold - actual
            display = f"{actual:.2f} vs {threshold:.2f} (need +{shortfall:.2f})"
        else:  # max
            # For maximum constraints: need actual <= threshold
            if threshold == 0:
                margin = 1.0 if actual > 0 else 0.0
            else:
                excess = actual - threshold
                margin = max(0, excess / threshold)
            excess = actual - threshold
            display = f"{actual:.2f} vs {threshold:.2f} (excess {excess:.2f})"

        return margin, display

    def apply_tradability_filters(
        self,
        candidate: CandidateStrike
    ) -> Tuple[List[RejectionReason], List[RejectionDetail]]:
        """
        Apply tradability filters to a candidate strike.

        Args:
            candidate: CandidateStrike to filter

        Returns:
            Tuple of (rejection_reasons, rejection_details)
            - rejection_reasons: List of RejectionReason enums
            - rejection_details: List of RejectionDetail with margin info
        """
        reasons = []
        details = []

        # Zero bid filter
        if candidate.bid <= 0:
            reasons.append(RejectionReason.ZERO_BID)
            details.append(RejectionDetail(
                reason=RejectionReason.ZERO_BID,
                actual_value=candidate.bid,
                threshold=0.01,
                margin=1.0,
                margin_display=f"bid=${candidate.bid:.2f} (no market)"
            ))

        # Low premium filter
        elif candidate.bid < self.config.min_bid_price:
            margin, display = self._calculate_margin(
                candidate.bid, self.config.min_bid_price, 'min'
            )
            reasons.append(RejectionReason.LOW_PREMIUM)
            details.append(RejectionDetail(
                reason=RejectionReason.LOW_PREMIUM,
                actual_value=candidate.bid,
                threshold=self.config.min_bid_price,
                margin=margin,
                margin_display=f"bid={display}"
            ))

        # Spread absolute filter
        if candidate.spread_absolute > self.config.max_spread_absolute:
            margin, display = self._calculate_margin(
                candidate.spread_absolute, self.config.max_spread_absolute, 'max'
            )
            reasons.append(RejectionReason.WIDE_SPREAD_ABSOLUTE)
            details.append(RejectionDetail(
                reason=RejectionReason.WIDE_SPREAD_ABSOLUTE,
                actual_value=candidate.spread_absolute,
                threshold=self.config.max_spread_absolute,
                margin=margin,
                margin_display=f"spread={display}"
            ))

        # Spread relative filter
        if candidate.spread_relative_pct > self.config.max_spread_relative_pct:
            margin, display = self._calculate_margin(
                candidate.spread_relative_pct, self.config.max_spread_relative_pct, 'max'
            )
            reasons.append(RejectionReason.WIDE_SPREAD_RELATIVE)
            details.append(RejectionDetail(
                reason=RejectionReason.WIDE_SPREAD_RELATIVE,
                actual_value=candidate.spread_relative_pct,
                threshold=self.config.max_spread_relative_pct,
                margin=margin,
                margin_display=f"spread%={display}"
            ))

        # Open interest filter
        if candidate.open_interest < self.config.min_open_interest:
            margin, display = self._calculate_margin(
                candidate.open_interest, self.config.min_open_interest, 'min'
            )
            reasons.append(RejectionReason.LOW_OPEN_INTEREST)
            details.append(RejectionDetail(
                reason=RejectionReason.LOW_OPEN_INTEREST,
                actual_value=candidate.open_interest,
                threshold=self.config.min_open_interest,
                margin=margin,
                margin_display=f"OI={int(candidate.open_interest)} vs {int(self.config.min_open_interest)}"
            ))

        # Volume filter
        if candidate.volume < self.config.min_volume:
            margin, display = self._calculate_margin(
                candidate.volume, self.config.min_volume, 'min'
            )
            reasons.append(RejectionReason.LOW_VOLUME)
            details.append(RejectionDetail(
                reason=RejectionReason.LOW_VOLUME,
                actual_value=candidate.volume,
                threshold=self.config.min_volume,
                margin=margin,
                margin_display=f"vol={int(candidate.volume)} vs {int(self.config.min_volume)}"
            ))

        # Net credit filter
        if candidate.cost_estimate.net_credit < self.config.min_net_credit:
            margin, display = self._calculate_margin(
                candidate.cost_estimate.net_credit, self.config.min_net_credit, 'min'
            )
            reasons.append(RejectionReason.NET_CREDIT_TOO_LOW)
            details.append(RejectionDetail(
                reason=RejectionReason.NET_CREDIT_TOO_LOW,
                actual_value=candidate.cost_estimate.net_credit,
                threshold=self.config.min_net_credit,
                margin=margin,
                margin_display=f"credit=${candidate.cost_estimate.net_credit:.2f} vs ${self.config.min_net_credit:.2f}"
            ))

        return reasons, details

    def apply_delta_band_filter(
        self,
        candidate: CandidateStrike
    ) -> Optional[RejectionDetail]:
        """
        Check if candidate delta is within the configured delta band.

        Args:
            candidate: CandidateStrike to check

        Returns:
            RejectionDetail if outside band, None if within band
        """
        target_band = self.config.delta_band
        min_delta, max_delta = DELTA_BAND_RANGES[target_band]
        delta = abs(candidate.delta)

        if min_delta <= delta < max_delta:
            return None  # Passes filter

        # Calculate margin - how far from the band edges
        if delta < min_delta:
            gap = min_delta - delta
            margin = gap / min_delta if min_delta > 0 else 1.0
            margin_display = f"delta={delta:.3f} < {min_delta:.2f} (need +{gap:.3f})"
        else:  # delta >= max_delta
            gap = delta - max_delta
            margin = gap / max_delta if max_delta > 0 else 1.0
            margin_display = f"delta={delta:.3f} > {max_delta:.2f} (excess {gap:.3f})"

        return RejectionDetail(
            reason=RejectionReason.OUTSIDE_DELTA_BAND,
            actual_value=delta,
            threshold=min_delta if delta < min_delta else max_delta,
            margin=margin,
            margin_display=margin_display
        )

    def calculate_near_miss_score(
        self,
        candidate: CandidateStrike,
        max_net_credit: float = 100.0
    ) -> float:
        """
        Calculate near-miss score for a rejected candidate.

        Higher score = closer to being recommended.
        Score combines:
        - Net credit potential (normalized, weight 0.6)
        - Inverse of rejection count (weight 0.2)
        - Inverse of minimum margin (weight 0.2)

        Args:
            candidate: Rejected CandidateStrike with rejection_details populated
            max_net_credit: Maximum expected net credit for normalization

        Returns:
            Near-miss score (0.0 to 1.0, higher = closer to passing)
        """
        if not candidate.rejection_details:
            return 1.0  # No rejections = perfect score

        # Net credit component (0-0.6): higher credit = better
        credit_score = min(1.0, candidate.total_net_credit / max_net_credit) * 0.6

        # Rejection count component (0-0.2): fewer rejections = better
        num_rejections = len(candidate.rejection_details)
        rejection_penalty = max(0, 1.0 - (num_rejections - 1) * 0.25)  # 1 rejection = 1.0, 5+ = 0
        rejection_score = rejection_penalty * 0.2

        # Minimum margin component (0-0.2): smaller margin = closer to passing
        min_margin = min(d.margin for d in candidate.rejection_details)
        margin_score = max(0, 1.0 - min_margin) * 0.2

        return credit_score + rejection_score + margin_score

    def populate_near_miss_details(
        self,
        candidate: CandidateStrike,
        max_net_credit: float = 100.0
    ) -> None:
        """
        Populate near-miss analysis fields on a rejected candidate.

        Sets:
        - rejection_details (already set by caller)
        - binding_constraint (constraint with smallest margin)
        - near_miss_score (weighted score)

        Args:
            candidate: CandidateStrike with rejection_details already populated
            max_net_credit: Maximum expected net credit for normalization
        """
        if not candidate.rejection_details:
            return

        # Find binding constraint (smallest margin)
        candidate.binding_constraint = min(
            candidate.rejection_details,
            key=lambda d: d.margin
        )

        # Calculate near-miss score
        candidate.near_miss_score = self.calculate_near_miss_score(
            candidate, max_net_credit
        )

    def generate_broker_checklist(
        self,
        symbol: str,
        candidate: CandidateStrike,
        earnings_clear: bool,
        dividend_verified: bool = False
    ) -> BrokerChecklist:
        """
        Generate a broker checklist for a recommended trade.

        Args:
            symbol: Stock symbol
            candidate: The recommended strike
            earnings_clear: Whether earnings have been verified clear
            dividend_verified: Whether dividend has been verified

        Returns:
            BrokerChecklist for the trade
        """
        checks = [
            f"Verify current bid >= ${candidate.bid:.2f}",
            f"Verify spread <= ${self.config.max_spread_absolute:.2f} or {self.config.max_spread_relative_pct:.0f}%",
            f"Verify open interest >= {self.config.min_open_interest}",
            f"Confirm {candidate.contracts_to_sell} contracts × ${candidate.strike} strike",
            f"Expected net credit: ${candidate.total_net_credit:.2f}",
        ]

        if earnings_clear:
            checks.append("Earnings: CLEAR (no earnings before expiration)")
        else:
            checks.append("Earnings: VERIFY at broker (data may be stale)")

        if dividend_verified:
            checks.append("Dividend: VERIFIED (no ex-div before expiration)")
        else:
            checks.append("Dividend: UNVERIFIED (check for early exercise risk)")

        warnings = list(candidate.warnings)
        if not dividend_verified:
            warnings.append("Dividend data unverified - check at broker")

        return BrokerChecklist(
            symbol=symbol,
            action="SELL TO OPEN",
            contracts=candidate.contracts_to_sell,
            strike=candidate.strike,
            expiration=candidate.expiration_date,
            option_type="CALL",
            limit_price=candidate.mid_price,
            min_acceptable_credit=candidate.bid,
            checks=checks,
            warnings=warnings
        )

    def generate_llm_memo_payload(
        self,
        symbol: str,
        current_price: float,
        holding: PortfolioHolding,
        candidate: CandidateStrike,
        earnings_status: str,
        dividend_status: str
    ) -> LLMMemoPayload:
        """
        Generate structured payload for LLM decision memo.

        Args:
            symbol: Stock symbol
            current_price: Current stock price
            holding: Portfolio holding info
            candidate: Recommended strike
            earnings_status: Earnings verification status
            dividend_status: Dividend verification status

        Returns:
            LLMMemoPayload for memo generation
        """
        holding_dict = {
            "symbol": holding.symbol,
            "shares": holding.shares,
            "cost_basis": holding.cost_basis,
            "acquired_date": holding.acquired_date,
            "account_type": holding.account_type,
        }

        return LLMMemoPayload(
            symbol=symbol,
            current_price=current_price,
            shares_held=holding.shares,
            contracts_to_write=candidate.contracts_to_sell,
            candidate=candidate.to_dict(),
            holding=holding_dict,
            risk_profile=self.config.delta_band.value,
            earnings_status=earnings_status,
            dividend_status=dividend_status,
            account_type=holding.account_type,
            timestamp=datetime.now().isoformat()
        )

    def scan_holding(
        self,
        holding: PortfolioHolding,
        current_price: float,
        options_chain: OptionsChain,
        volatility: float,
        override_earnings_check: bool = False
    ) -> ScanResult:
        """
        Scan a single holding for covered call opportunities.

        Args:
            holding: Portfolio holding to scan
            current_price: Current stock price
            options_chain: Options chain for the symbol
            volatility: Annualized volatility for delta calculations
            override_earnings_check: If True, include earnings-week expirations

        Returns:
            ScanResult with recommendations and rejected strikes
        """
        symbol = holding.symbol
        contracts_available = self.calculate_contracts_to_sell(holding.shares)

        result = ScanResult(
            symbol=symbol,
            current_price=current_price,
            shares_held=holding.shares,
            contracts_available=contracts_available
        )

        # Check if holding is actionable
        if contracts_available == 0:
            result.error = f"Non-actionable: {holding.shares} shares < 100 shares minimum for 1 contract with {self.config.overwrite_cap_pct}% cap"
            result.warnings.append("Insufficient shares for contract sizing")
            return result

        # Get earnings dates
        earnings_dates = self.earnings_calendar.get_earnings_dates(symbol)
        result.earnings_dates = earnings_dates

        # Get call options
        calls = options_chain.get_calls()
        if not calls:
            result.error = "No call options found in chain"
            return result

        # Get weekly expirations
        expirations = sorted(set(c.expiration_date for c in calls))[:self.config.weeks_to_scan]

        recommended = []
        rejected = []

        for exp_date in expirations:
            # Check earnings exclusion
            spans_earnings, earn_date = self.earnings_calendar.expiration_spans_earnings(
                symbol, exp_date
            )

            if spans_earnings and not override_earnings_check and self.config.skip_earnings_default:
                result.has_earnings_conflict = True
                logger.info(f"Skipping {exp_date} - spans earnings on {earn_date}")
                continue

            # Calculate days to expiry
            try:
                exp_dt = datetime.fromisoformat(exp_date)
                days_to_expiry = max(1, (exp_dt - datetime.now()).days)
            except ValueError:
                days_to_expiry = 7  # Default fallback

            # Get calls for this expiration
            exp_calls = [c for c in calls if c.expiration_date == exp_date]

            for contract in exp_calls:
                # Skip ITM calls
                if contract.strike <= current_price:
                    continue

                # Skip if no bid/ask
                if contract.bid is None or contract.ask is None:
                    continue

                bid = contract.bid or 0
                ask = contract.ask or 0

                if ask <= 0:
                    continue

                mid_price = (bid + ask) / 2
                spread_absolute = ask - bid
                spread_relative_pct = (spread_absolute / mid_price * 100) if mid_price > 0 else 100

                # Compute delta using Black-Scholes
                delta, p_itm = self.compute_delta(
                    strike=contract.strike,
                    current_price=current_price,
                    volatility=volatility,
                    days_to_expiry=days_to_expiry,
                    option_type="call"
                )

                # Compute sigma distance for diagnostic
                try:
                    sigma_distance = self.optimizer.get_sigma_for_strike(
                        strike=contract.strike,
                        current_price=current_price,
                        volatility=volatility,
                        days_to_expiry=days_to_expiry,
                        option_type="call"
                    )
                except (ValueError, ZeroDivisionError):
                    sigma_distance = None

                # Get delta band
                delta_band = self.get_delta_band(delta)

                # Calculate execution cost
                cost_estimate = self.calculate_execution_cost(
                    bid=bid,
                    ask=ask,
                    contracts=contracts_available
                )

                # Calculate annualized yield
                position_value = current_price * 100 * contracts_available
                if position_value > 0 and days_to_expiry > 0:
                    annualized_yield = (cost_estimate.net_credit / position_value) * (365 / days_to_expiry) * 100
                else:
                    annualized_yield = 0

                candidate = CandidateStrike(
                    contract=contract,
                    strike=contract.strike,
                    expiration_date=exp_date,
                    delta=delta,
                    p_itm=p_itm,
                    sigma_distance=sigma_distance,
                    bid=bid,
                    ask=ask,
                    mid_price=mid_price,
                    spread_absolute=spread_absolute,
                    spread_relative_pct=spread_relative_pct,
                    open_interest=contract.open_interest or 0,
                    volume=contract.volume or 0,
                    cost_estimate=cost_estimate,
                    delta_band=delta_band,
                    contracts_to_sell=contracts_available,
                    total_net_credit=cost_estimate.net_credit,
                    annualized_yield_pct=annualized_yield,
                    days_to_expiry=days_to_expiry
                )

                # Apply tradability filters (returns tuple of reasons and details)
                rejection_reasons, rejection_details = self.apply_tradability_filters(candidate)

                # Check delta band filter
                delta_detail = self.apply_delta_band_filter(candidate)
                if delta_detail:
                    rejection_reasons.append(RejectionReason.OUTSIDE_DELTA_BAND)
                    rejection_details.append(delta_detail)

                # Check earnings if applicable
                if spans_earnings:
                    rejection_reasons.append(RejectionReason.EARNINGS_WEEK)
                    rejection_details.append(RejectionDetail(
                        reason=RejectionReason.EARNINGS_WEEK,
                        actual_value=1.0,
                        threshold=0.0,
                        margin=1.0,  # Hard gate - no partial margin
                        margin_display=f"earnings on {earn_date} before {exp_date}"
                    ))
                    candidate.warnings.append(f"Expiration spans earnings on {earn_date}")

                if rejection_reasons:
                    candidate.rejection_reasons = rejection_reasons
                    candidate.rejection_details = rejection_details
                    candidate.is_recommended = False
                    rejected.append(candidate)
                else:
                    recommended.append(candidate)

        # Sort recommended by net credit (highest first)
        recommended.sort(key=lambda c: c.total_net_credit, reverse=True)

        # Calculate near-miss scores for rejected candidates
        max_net_credit = max(
            (c.total_net_credit for c in rejected),
            default=100.0
        ) or 100.0

        for candidate in rejected:
            self.populate_near_miss_details(candidate, max_net_credit)

        # Get top 5 near-miss candidates (sorted by score, highest first)
        near_misses = sorted(rejected, key=lambda c: c.near_miss_score, reverse=True)[:5]

        result.recommended_strikes = recommended
        result.rejected_strikes = rejected
        result.near_miss_candidates = near_misses

        # Generate broker checklist and LLM memo for top recommendation
        if recommended:
            top = recommended[0]
            earnings_clear = not result.has_earnings_conflict

            result.broker_checklist = self.generate_broker_checklist(
                symbol=symbol,
                candidate=top,
                earnings_clear=earnings_clear,
                dividend_verified=False  # TODO: Add dividend checking
            )

            earnings_status = "CLEAR" if earnings_clear else "UNVERIFIED"
            dividend_status = "UNVERIFIED"

            result.llm_memo_payload = self.generate_llm_memo_payload(
                symbol=symbol,
                current_price=current_price,
                holding=holding,
                candidate=top,
                earnings_status=earnings_status,
                dividend_status=dividend_status
            )

        logger.info(
            f"Scanned {symbol}: {len(recommended)} recommended, "
            f"{len(rejected)} rejected, contracts={contracts_available}"
        )

        return result

    def scan_portfolio(
        self,
        holdings: List[PortfolioHolding],
        current_prices: Dict[str, float],
        options_chains: Dict[str, OptionsChain],
        volatilities: Dict[str, float],
        override_earnings_check: bool = False
    ) -> Dict[str, ScanResult]:
        """
        Scan entire portfolio for covered call opportunities.

        Args:
            holdings: List of portfolio holdings
            current_prices: Map of symbol -> current price
            options_chains: Map of symbol -> options chain
            volatilities: Map of symbol -> annualized volatility
            override_earnings_check: If True, include earnings-week expirations

        Returns:
            Dictionary mapping symbol to ScanResult
        """
        results = {}

        for holding in holdings:
            symbol = holding.symbol

            # Check if we have required data
            if symbol not in current_prices:
                results[symbol] = ScanResult(
                    symbol=symbol,
                    current_price=0,
                    shares_held=holding.shares,
                    contracts_available=0,
                    error=f"No price data for {symbol}"
                )
                continue

            if symbol not in options_chains:
                results[symbol] = ScanResult(
                    symbol=symbol,
                    current_price=current_prices[symbol],
                    shares_held=holding.shares,
                    contracts_available=0,
                    error=f"No options chain for {symbol}"
                )
                continue

            if symbol not in volatilities:
                results[symbol] = ScanResult(
                    symbol=symbol,
                    current_price=current_prices[symbol],
                    shares_held=holding.shares,
                    contracts_available=0,
                    error=f"No volatility data for {symbol}"
                )
                continue

            # Scan the holding
            result = self.scan_holding(
                holding=holding,
                current_price=current_prices[symbol],
                options_chain=options_chains[symbol],
                volatility=volatilities[symbol],
                override_earnings_check=override_earnings_check
            )

            results[symbol] = result

        logger.info(f"Scanned {len(holdings)} holdings, {len(results)} results")
        return results

    def generate_trade_blotter(
        self,
        scan_results: Dict[str, ScanResult],
        top_n: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Generate a trade blotter from scan results.

        The blotter shows the top N recommendations per symbol,
        ranked by net credit.

        Args:
            scan_results: Dictionary of scan results
            top_n: Maximum recommendations per symbol

        Returns:
            List of trade entries for the blotter
        """
        blotter = []

        for symbol, result in scan_results.items():
            if result.error:
                blotter.append({
                    "symbol": symbol,
                    "status": "ERROR",
                    "error": result.error,
                    "recommendations": []
                })
                continue

            if not result.recommended_strikes:
                blotter.append({
                    "symbol": symbol,
                    "status": "NO_RECOMMENDATIONS",
                    "rejected_count": len(result.rejected_strikes),
                    "recommendations": []
                })
                continue

            recommendations = []
            for strike in result.recommended_strikes[:top_n]:
                recommendations.append({
                    "strike": strike.strike,
                    "expiration": strike.expiration_date,
                    "contracts": strike.contracts_to_sell,
                    "net_credit": round(strike.total_net_credit, 2),
                    "delta": round(strike.delta, 3),
                    "annualized_yield_pct": round(strike.annualized_yield_pct, 2),
                    "delta_band": strike.delta_band.value if strike.delta_band else None,
                })

            blotter.append({
                "symbol": symbol,
                "status": "OK",
                "current_price": round(result.current_price, 2),
                "shares": result.shares_held,
                "contracts_available": result.contracts_available,
                "earnings_clear": not result.has_earnings_conflict,
                "recommendations": recommendations,
                "broker_checklist": result.broker_checklist.to_dict() if result.broker_checklist else None,
            })

        # Sort by total potential net credit
        blotter.sort(
            key=lambda x: x.get("recommendations", [{}])[0].get("net_credit", 0)
            if x.get("recommendations") else 0,
            reverse=True
        )

        return blotter
