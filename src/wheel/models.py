"""Data models for wheel strategy positions and trades."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from src.models.profiles import StrikeProfile

from .state import TradeOutcome, WheelState


@dataclass
class WheelPosition:
    """
    Represents a wheel position on a single symbol.

    Tracks the current state, capital allocation, and share holdings
    for a wheel strategy on one underlying stock.
    """

    id: Optional[int] = None
    symbol: str = ""
    state: WheelState = WheelState.CASH
    capital_allocated: float = 0.0
    shares_held: int = 0
    cost_basis: Optional[float] = None  # Avg cost per share when holding
    profile: StrikeProfile = StrikeProfile.CONSERVATIVE
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    is_active: bool = True

    @property
    def can_sell_put(self) -> bool:
        """Can only sell puts when in CASH state (not SHARES)."""
        return self.state == WheelState.CASH

    @property
    def can_sell_call(self) -> bool:
        """Can only sell calls when in SHARES state."""
        return self.state == WheelState.SHARES

    @property
    def has_open_position(self) -> bool:
        """True if awaiting expiration on a sold option."""
        return self.state in (WheelState.CASH_PUT_OPEN, WheelState.SHARES_CALL_OPEN)

    @property
    def contracts_from_shares(self) -> int:
        """Number of covered call contracts available from shares."""
        return self.shares_held // 100

    def contracts_from_capital(self, strike: float) -> int:
        """
        Number of cash-secured put contracts available.

        Args:
            strike: The strike price for the put option.

        Returns:
            Maximum number of contracts that can be collateralized.
        """
        if strike <= 0:
            return 0
        collateral_per_contract = strike * 100
        return int(self.capital_allocated // collateral_per_contract)


@dataclass
class TradeRecord:
    """
    Records a single option trade (selling a put or call).

    Tracks all details from opening to closing/expiration.
    """

    id: Optional[int] = None
    wheel_id: int = 0
    symbol: str = ""
    direction: str = ""  # "put" or "call"
    strike: float = 0.0
    expiration_date: str = ""  # YYYY-MM-DD
    premium_per_share: float = 0.0
    contracts: int = 0
    total_premium: float = 0.0  # premium_per_share * contracts * 100
    opened_at: datetime = field(default_factory=datetime.now)
    closed_at: Optional[datetime] = None
    outcome: TradeOutcome = TradeOutcome.OPEN
    price_at_expiry: Optional[float] = None
    close_price: Optional[float] = None  # For early closes

    def __post_init__(self) -> None:
        """Calculate total premium if not set."""
        if self.total_premium == 0.0 and self.premium_per_share > 0:
            self.total_premium = self.premium_per_share * self.contracts * 100

    @property
    def shares_equivalent(self) -> int:
        """Number of shares represented by this trade."""
        return self.contracts * 100

    @property
    def net_premium(self) -> float:
        """Net premium after any close costs."""
        if self.close_price is not None and self.outcome == TradeOutcome.CLOSED_EARLY:
            close_cost = self.close_price * self.contracts * 100
            return self.total_premium - close_cost
        return self.total_premium

    @property
    def is_open(self) -> bool:
        """True if trade is still open."""
        return self.outcome == TradeOutcome.OPEN


@dataclass
class WheelRecommendation:
    """A recommendation for the next option to sell."""

    symbol: str
    direction: str  # "put" or "call"
    strike: float
    expiration_date: str
    premium_per_share: float
    contracts: int
    total_premium: float
    sigma_distance: float
    p_itm: float
    annualized_yield_pct: float
    warnings: list[str] = field(default_factory=list)

    # Bias indicators
    bias_score: float = 0.0  # Higher = more likely to expire worthless
    dte: int = 0

    # Market context
    current_price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0

    @property
    def effective_yield_if_assigned(self) -> float:
        """
        For puts: Effective cost basis if assigned (strike - premium).
        For calls: Effective sale price if called away (strike + premium).
        """
        if self.direction == "put":
            return self.strike - self.premium_per_share
        else:  # call
            return self.strike + self.premium_per_share


@dataclass
class WheelPerformance:
    """Performance metrics for a wheel position or portfolio."""

    symbol: str  # "ALL" for portfolio-wide metrics
    total_premium: float = 0.0  # All premium collected
    total_trades: int = 0
    winning_trades: int = 0  # Expired worthless
    assignment_events: int = 0  # Times put was assigned
    called_away_events: int = 0  # Times call was exercised
    closed_early_count: int = 0  # Times bought back early
    win_rate_pct: float = 0.0  # winning_trades / (total_trades - open_trades)
    puts_sold: int = 0
    calls_sold: int = 0
    average_days_held: float = 0.0
    annualized_yield_pct: float = 0.0
    realized_pnl: float = 0.0  # Net P&L including assignment costs
    current_state: WheelState = WheelState.CASH
    current_shares: int = 0
    current_cost_basis: Optional[float] = None
    capital_deployed: float = 0.0  # Current capital in use
    open_trades: int = 0  # Currently open positions

    @property
    def completed_trades(self) -> int:
        """Number of trades that have closed."""
        return self.total_trades - self.open_trades

    @property
    def loss_rate_pct(self) -> float:
        """Percentage of trades that resulted in assignment/exercise."""
        if self.completed_trades == 0:
            return 0.0
        return (
            (self.assignment_events + self.called_away_events)
            / self.completed_trades
            * 100
        )
