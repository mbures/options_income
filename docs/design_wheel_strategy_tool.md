# System Design Document: Wheel Strategy Tool

## 1. Architecture Overview

### 1.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        wheel_strategy_tool.py                    │
├─────────────────────────────────────────────────────────────────┤
│  CLI Layer (click)           │  Module API (WheelManager)       │
│  - wheel init                │  - create_wheel()                │
│  - wheel recommend           │  - get_recommendation()          │
│  - wheel record              │  - record_trade()                │
│  - wheel expire              │  - record_expiration()           │
│  - wheel status              │  - get_status()                  │
│  - wheel performance         │  - get_performance()             │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Core Components                             │
├──────────────────┬──────────────────┬───────────────────────────┤
│  WheelManager    │  RecommendEngine │  PerformanceTracker       │
│  - State machine │  - Strike select │  - Metrics calculation    │
│  - CRUD ops      │  - Bias logic    │  - Aggregation            │
│  - Validation    │  - Warnings      │  - Export                 │
└──────────────────┴──────────────────┴───────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Persistence Layer                            │
├─────────────────────────────────────────────────────────────────┤
│  WheelRepository (SQLite)                                       │
│  - wheels table                                                 │
│  - trades table                                                 │
│  - Connection management                                        │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Existing Infrastructure                        │
├──────────────────┬──────────────────┬───────────────────────────┤
│  StrikeOptimizer │  FinnhubClient   │  VolatilityCalculator     │
│  CoveredStrategies│ PriceFetcher    │  EarningsCalendar         │
└──────────────────┴──────────────────┴───────────────────────────┘
```

### 1.2 Component Responsibilities

| Component | Responsibility |
|-----------|---------------|
| CLI Layer | Parse commands, format output, handle errors |
| WheelManager | Orchestrate operations, enforce state machine |
| RecommendEngine | Generate biased strike recommendations |
| PerformanceTracker | Calculate and aggregate metrics |
| WheelRepository | SQLite persistence, queries |
| Existing Infrastructure | Market data, calculations |

---

## 2. Module Structure

### 2.1 File Organization

```
wheel_strategy_tool.py          # Main entry point (CLI + exports)
src/
  wheel/                        # New package
    __init__.py                 # Public API exports
    manager.py                  # WheelManager class
    recommend.py                # RecommendEngine class
    performance.py              # PerformanceTracker class
    repository.py               # WheelRepository (SQLite)
    models.py                   # Data classes (WheelPosition, TradeRecord, etc.)
    state.py                    # WheelState enum and transitions
    cli.py                      # Click CLI implementation
```

### 2.2 Public API (wheel_strategy_tool.py)

```python
"""
Wheel Strategy Tool - CLI and Module for managing options wheel strategies.

CLI Usage:
    wheel init AAPL --capital 10000 --profile conservative
    wheel recommend AAPL
    wheel record AAPL put --strike 145 --expiration 2025-02-21 --premium 1.50

Module Usage:
    from wheel_strategy_tool import WheelManager

    manager = WheelManager()
    manager.create_wheel("AAPL", capital=10000, profile="conservative")
    rec = manager.get_recommendation("AAPL")
"""

from src.wheel import (
    WheelManager,
    WheelPosition,
    TradeRecord,
    WheelPerformance,
    WheelState,
    TradeOutcome,
)

__all__ = [
    "WheelManager",
    "WheelPosition",
    "TradeRecord",
    "WheelPerformance",
    "WheelState",
    "TradeOutcome",
]

def main():
    """CLI entry point."""
    from src.wheel.cli import cli
    cli()

if __name__ == "__main__":
    main()
```

---

## 3. Data Models

### 3.1 Enums

```python
# src/wheel/state.py

from enum import Enum

class WheelState(Enum):
    """
    State machine for wheel positions.

    The wheel alternates between two fundamental states:
    - CASH: Have capital, can sell puts (hoping to NOT get assigned)
    - SHARES: Have shares, can sell calls (hoping to NOT get called away)

    Open positions track when an option is sold and awaiting expiration.
    """
    CASH = "cash"                      # Have capital, no shares, can sell puts
    CASH_PUT_OPEN = "cash_put_open"    # Sold put, awaiting expiration
    SHARES = "shares"                  # Have shares, can sell calls
    SHARES_CALL_OPEN = "shares_call_open"  # Sold call, awaiting expiration

class TradeOutcome(Enum):
    """Possible outcomes for a trade."""
    OPEN = "open"                      # Trade still active
    EXPIRED_WORTHLESS = "expired_worthless"  # Option expired OTM - KEEP PREMIUM
    ASSIGNED = "assigned"              # Put assigned - BOUGHT SHARES at strike
    CALLED_AWAY = "called_away"        # Call exercised - SOLD SHARES at strike
    CLOSED_EARLY = "closed_early"      # Bought back before expiration
```

### 3.2 State Transitions

The wheel strategy cycles between having CASH and having SHARES:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        WHEEL STRATEGY STATE MACHINE                      │
└─────────────────────────────────────────────────────────────────────────┘

                         ┌──────────────────┐
                         │                  │
        ┌───────────────►│      CASH        │◄───────────────┐
        │                │  (have capital)  │                │
        │                └────────┬─────────┘                │
        │                         │                          │
        │                         │ SELL PUT                 │
        │                         │ (collect premium)        │
        │                         ▼                          │
        │                ┌──────────────────┐                │
        │                │                  │                │
        │                │  CASH_PUT_OPEN   │                │
        │                │ (awaiting expiry)│                │
        │                └────────┬─────────┘                │
        │                         │                          │
        │           ┌─────────────┴─────────────┐            │
        │           │                           │            │
        │           ▼                           ▼            │
        │    EXPIRED OTM                   ASSIGNED          │
        │    (keep premium)            (bought shares)       │
        │           │                           │            │
        │           │                           │            │
        └───────────┘                           │            │
                                               ▼            │
                         ┌──────────────────┐                │
                         │                  │                │
        ┌───────────────►│     SHARES       │                │
        │                │  (have shares)   │                │
        │                └────────┬─────────┘                │
        │                         │                          │
        │                         │ SELL CALL                │
        │                         │ (collect premium)        │
        │                         ▼                          │
        │                ┌──────────────────┐                │
        │                │                  │                │
        │                │ SHARES_CALL_OPEN │                │
        │                │ (awaiting expiry)│                │
        │                └────────┬─────────┘                │
        │                         │                          │
        │           ┌─────────────┴─────────────┐            │
        │           │                           │            │
        │           ▼                           ▼            │
        │    EXPIRED OTM                  CALLED AWAY        │
        │    (keep premium)             (sold shares)        │
        │           │                           │            │
        └───────────┘                           └────────────┘


PREMIUM IS COLLECTED EVERY TIME AN OPTION IS SOLD (regardless of outcome)

WINNING TRADE = Option expires worthless (OTM) - you keep premium, position unchanged
ASSIGNMENT   = Put was ITM - you bought shares at strike (now have shares, not cash)
CALLED AWAY  = Call was ITM - you sold shares at strike (now have cash, not shares)
```

### 3.3 Valid State Transitions

| From State | Action | Outcome | To State |
|------------|--------|---------|----------|
| CASH | Sell Put | - | CASH_PUT_OPEN |
| CASH_PUT_OPEN | Expiry | Expired OTM | CASH |
| CASH_PUT_OPEN | Expiry | Assigned | SHARES |
| SHARES | Sell Call | - | SHARES_CALL_OPEN |
| SHARES_CALL_OPEN | Expiry | Expired OTM | SHARES |
| SHARES_CALL_OPEN | Expiry | Called Away | CASH |

### 3.4 Data Classes

```python
# src/wheel/models.py

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from .state import WheelState, TradeOutcome
from src.models.profiles import StrikeProfile

@dataclass
class WheelPosition:
    """Represents a wheel position on a single symbol."""
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

    # Computed properties
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
    def available_contracts(self) -> int:
        """Number of contracts that can be sold."""
        if self.state == WheelState.CASH:
            # For puts: depends on capital and strike (calculated at recommendation time)
            return 0  # Placeholder - calculated dynamically
        elif self.state == WheelState.SHARES:
            return self.shares_held // 100
        return 0

@dataclass
class TradeRecord:
    """Records a single option trade (selling a put or call)."""
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

    def __post_init__(self):
        if self.total_premium == 0.0 and self.premium_per_share > 0:
            self.total_premium = self.premium_per_share * self.contracts * 100

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

@dataclass
class WheelPerformance:
    """Performance metrics for a wheel position."""
    symbol: str
    total_premium: float = 0.0          # All premium collected
    total_trades: int = 0
    winning_trades: int = 0             # Expired worthless
    assignment_events: int = 0          # Times put was assigned
    called_away_events: int = 0         # Times call was exercised
    win_rate_pct: float = 0.0           # winning_trades / total_trades
    puts_sold: int = 0
    calls_sold: int = 0
    average_days_held: float = 0.0
    annualized_yield_pct: float = 0.0
    realized_pnl: float = 0.0           # Premium - losses from assignment/exercise
    current_state: WheelState = WheelState.CASH
    current_shares: int = 0
    current_cost_basis: Optional[float] = None
```

---

## 4. Core Components

### 4.1 WheelManager

```python
# src/wheel/manager.py

class WheelManager:
    """
    Main orchestrator for wheel strategy operations.

    Manages the lifecycle of wheel positions, enforces state machine
    rules, and coordinates between components.
    """

    def __init__(
        self,
        db_path: str = "~/.wheel_strategy/trades.db",
        finnhub_client: Optional[FinnhubClient] = None,
        price_fetcher: Optional[AlphaVantagePriceDataFetcher] = None,
    ):
        self.repository = WheelRepository(db_path)
        self.recommend_engine = RecommendEngine(finnhub_client, price_fetcher)
        self.performance_tracker = PerformanceTracker(self.repository)

    # Wheel CRUD
    def create_wheel(
        self,
        symbol: str,
        capital: float,
        profile: str = "conservative",
        starting_direction: Optional[str] = None,
    ) -> WheelPosition:
        """
        Create a new wheel position starting with cash.

        Args:
            symbol: Stock ticker
            capital: Cash allocated for this wheel
            profile: Risk profile (aggressive/moderate/conservative/defensive)
            starting_direction: Optional override - normally starts with puts
        """
        ...

    def import_shares(
        self,
        symbol: str,
        shares: int,
        cost_basis: float,
        capital: float = 0.0,
        profile: str = "conservative",
    ) -> WheelPosition:
        """
        Import existing shares to start selling calls immediately.

        Creates wheel in SHARES state instead of CASH state.
        """
        ...

    def get_wheel(self, symbol: str) -> Optional[WheelPosition]: ...

    def list_wheels(self, active_only: bool = True) -> list[WheelPosition]: ...

    def close_wheel(self, symbol: str) -> None: ...

    # Recommendations
    def get_recommendation(self, symbol: str) -> WheelRecommendation:
        """
        Get recommendation based on current state:
        - CASH state → recommend put to sell
        - SHARES state → recommend call to sell
        - OPEN states → error (must wait for expiration)
        """
        ...

    def get_all_recommendations(self) -> list[WheelRecommendation]: ...

    # Trade recording
    def record_trade(
        self,
        symbol: str,
        direction: str,
        strike: float,
        expiration_date: str,
        premium: float,
        contracts: int,
    ) -> TradeRecord:
        """
        Record a sold option. Validates state allows this direction.

        - Selling put: must be in CASH state → transitions to CASH_PUT_OPEN
        - Selling call: must be in SHARES state → transitions to SHARES_CALL_OPEN
        """
        ...

    def record_expiration(
        self,
        symbol: str,
        price_at_expiry: float,
    ) -> TradeOutcome:
        """
        Record expiration outcome and transition state.

        Determines if option expired worthless or was assigned/exercised
        based on price_at_expiry vs strike.

        PUT expired OTM (price > strike): CASH_PUT_OPEN → CASH
        PUT assigned (price <= strike): CASH_PUT_OPEN → SHARES
        CALL expired OTM (price < strike): SHARES_CALL_OPEN → SHARES
        CALL called away (price >= strike): SHARES_CALL_OPEN → CASH
        """
        ...

    def close_trade_early(
        self,
        symbol: str,
        close_price: float,
    ) -> TradeRecord:
        """Buy back option early (before expiration)."""
        ...

    # Performance
    def get_performance(self, symbol: str) -> WheelPerformance: ...

    def get_portfolio_performance(self) -> WheelPerformance: ...

    def export_trades(
        self,
        symbol: Optional[str] = None,
        format: str = "csv",
    ) -> str: ...
```

### 4.2 RecommendEngine

```python
# src/wheel/recommend.py

class RecommendEngine:
    """
    Generates biased recommendations favoring premium collection.

    The goal is to COLLECT PREMIUM while AVOIDING ASSIGNMENT.

    Bias strategies:
    1. Select strikes toward the outer edge of profile sigma range (further OTM)
    2. Prefer shorter-dated expirations (less time for adverse price moves)
    3. Warn on high P(ITM) or event conflicts
    """

    def __init__(
        self,
        finnhub_client: Optional[FinnhubClient] = None,
        price_fetcher: Optional[AlphaVantagePriceDataFetcher] = None,
    ):
        self.finnhub = finnhub_client or FinnhubClient(...)
        self.price_fetcher = price_fetcher or AlphaVantagePriceDataFetcher(...)
        self.strike_optimizer = StrikeOptimizer()
        self.volatility_calculator = VolatilityCalculator
        self.earnings_calendar = EarningsCalendar(self.finnhub)

    def get_recommendation(
        self,
        position: WheelPosition,
    ) -> WheelRecommendation:
        """
        Generate a biased recommendation for the next trade.

        For CASH state: recommend a PUT to sell (further OTM = less likely to buy shares)
        For SHARES state: recommend a CALL to sell (further OTM = less likely to sell shares)
        """

        # Determine direction from state
        if position.state == WheelState.CASH:
            direction = "put"
        elif position.state == WheelState.SHARES:
            direction = "call"
        else:
            raise InvalidStateError(f"Cannot recommend in state {position.state}")

        # Fetch market data
        current_price = self._fetch_current_price(position.symbol)
        options_chain = self._fetch_options_chain(position.symbol)
        volatility = self._calculate_volatility(position.symbol)

        # Get candidates within profile range
        candidates = self._get_candidates(
            options_chain=options_chain,
            current_price=current_price,
            volatility=volatility,
            direction=direction,
            profile=position.profile,
        )

        # Apply bias: prefer further OTM + shorter DTE
        biased = self._apply_collection_bias(candidates)

        # Add warnings
        self._add_warnings(biased, position.symbol)

        return biased[0] if biased else None

    def _apply_collection_bias(
        self,
        candidates: list[WheelRecommendation],
    ) -> list[WheelRecommendation]:
        """
        Score and sort candidates by "collection bias" - preference for
        options that will expire worthless (letting us keep premium).

        Bias scoring:
        - Higher sigma distance = better (further OTM, less likely to be ITM)
        - Lower DTE = better (less time for adverse price moves)
        - Lower P(ITM) = better (less assignment/exercise risk)
        """
        for c in candidates:
            # Normalize factors to 0-1 scale
            sigma_score = min(c.sigma_distance / 2.5, 1.0)  # Cap at 2.5σ
            dte_score = 1.0 - min(c.dte / 45, 1.0)  # Prefer < 45 DTE
            pitm_score = 1.0 - c.p_itm  # Lower P(ITM) = higher score

            # Weighted combination favoring low assignment probability
            c.bias_score = (
                0.4 * sigma_score +
                0.3 * dte_score +
                0.3 * pitm_score
            )

        return sorted(candidates, key=lambda c: c.bias_score, reverse=True)

    def _add_warnings(
        self,
        candidates: list[WheelRecommendation],
        symbol: str,
    ) -> None:
        """Add warnings for conditions that increase assignment risk."""
        for c in candidates:
            # High P(ITM) warning - increased risk of assignment
            threshold = self._get_pitm_threshold(c.profile)
            if c.p_itm > threshold:
                c.warnings.append(
                    f"P(ITM) {c.p_itm*100:.1f}% exceeds {threshold*100:.0f}% threshold - higher assignment risk"
                )

            # Earnings warning - volatility spike risk
            spans, earn_date = self.earnings_calendar.expiration_spans_earnings(
                symbol, c.expiration_date
            )
            if spans:
                c.warnings.append(f"Earnings on {earn_date} - elevated volatility risk")

            # Low premium warning - may not be worth the risk
            if c.annualized_yield_pct < 5.0:
                c.warnings.append(
                    f"Low annualized yield: {c.annualized_yield_pct:.1f}%"
                )
```

### 4.3 WheelRepository

```python
# src/wheel/repository.py

class WheelRepository:
    """SQLite persistence for wheel positions and trades."""

    def __init__(self, db_path: str):
        self.db_path = os.path.expanduser(db_path)
        self._ensure_directory()
        self._init_database()

    def _init_database(self) -> None:
        """Create tables if they don't exist."""
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS wheels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL UNIQUE,
                    state TEXT NOT NULL DEFAULT 'cash',
                    capital_allocated REAL NOT NULL DEFAULT 0,
                    shares_held INTEGER NOT NULL DEFAULT 0,
                    cost_basis REAL,
                    profile TEXT NOT NULL DEFAULT 'conservative',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    wheel_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    strike REAL NOT NULL,
                    expiration_date TEXT NOT NULL,
                    premium_per_share REAL NOT NULL,
                    contracts INTEGER NOT NULL,
                    total_premium REAL NOT NULL,
                    opened_at TEXT NOT NULL,
                    closed_at TEXT,
                    outcome TEXT NOT NULL DEFAULT 'open',
                    price_at_expiry REAL,
                    FOREIGN KEY (wheel_id) REFERENCES wheels(id)
                );

                CREATE INDEX IF NOT EXISTS idx_trades_wheel
                    ON trades(wheel_id);
                CREATE INDEX IF NOT EXISTS idx_trades_symbol
                    ON trades(symbol);
                CREATE INDEX IF NOT EXISTS idx_wheels_symbol
                    ON wheels(symbol);
            """)

    # Wheel operations
    def create_wheel(self, position: WheelPosition) -> WheelPosition: ...
    def get_wheel(self, symbol: str) -> Optional[WheelPosition]: ...
    def update_wheel(self, position: WheelPosition) -> None: ...
    def list_wheels(self, active_only: bool = True) -> list[WheelPosition]: ...

    # Trade operations
    def create_trade(self, trade: TradeRecord) -> TradeRecord: ...
    def get_open_trade(self, wheel_id: int) -> Optional[TradeRecord]: ...
    def update_trade(self, trade: TradeRecord) -> None: ...
    def get_trades(
        self,
        symbol: Optional[str] = None,
        outcome: Optional[TradeOutcome] = None,
    ) -> list[TradeRecord]: ...
```

---

## 5. CLI Implementation

### 5.1 Command Structure

```python
# src/wheel/cli.py

import click
from .manager import WheelManager

@click.group()
@click.option('--db', default='~/.wheel_strategy/trades.db', help='Database path')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
@click.option('--json', 'output_json', is_flag=True, help='JSON output')
@click.pass_context
def cli(ctx, db, verbose, output_json):
    """Wheel Strategy Tool - Manage options wheel positions."""
    ctx.ensure_object(dict)
    ctx.obj['manager'] = WheelManager(db_path=db)
    ctx.obj['verbose'] = verbose
    ctx.obj['json'] = output_json

@cli.command()
@click.argument('symbol')
@click.option('--capital', required=True, type=float, help='Capital allocation')
@click.option('--profile', default='conservative',
              type=click.Choice(['aggressive', 'moderate', 'conservative', 'defensive']))
@click.option('--direction', type=click.Choice(['put', 'call']), help='Starting direction')
@click.pass_context
def init(ctx, symbol, capital, profile, direction):
    """Initialize a new wheel position (starts in CASH state, ready to sell puts)."""
    manager = ctx.obj['manager']
    wheel = manager.create_wheel(
        symbol=symbol.upper(),
        capital=capital,
        profile=profile,
        starting_direction=direction,
    )
    click.echo(f"Created wheel for {wheel.symbol} with ${capital:,.2f} capital")
    click.echo(f"Profile: {profile}, State: {wheel.state.value}")
    click.echo(f"Ready to sell puts (use 'wheel recommend {wheel.symbol}')")

@cli.command('import')
@click.argument('symbol')
@click.option('--shares', required=True, type=int, help='Number of shares')
@click.option('--cost-basis', required=True, type=float, help='Cost per share')
@click.option('--capital', default=0.0, type=float, help='Additional capital')
@click.option('--profile', default='conservative',
              type=click.Choice(['aggressive', 'moderate', 'conservative', 'defensive']))
@click.pass_context
def import_shares(ctx, symbol, shares, cost_basis, capital, profile):
    """Import existing shares (starts in SHARES state, ready to sell calls)."""
    manager = ctx.obj['manager']
    wheel = manager.import_shares(
        symbol=symbol.upper(),
        shares=shares,
        cost_basis=cost_basis,
        capital=capital,
        profile=profile,
    )
    click.echo(f"Imported {shares} shares of {wheel.symbol} @ ${cost_basis:.2f}")
    click.echo(f"State: {wheel.state.value}")
    click.echo(f"Ready to sell calls (use 'wheel recommend {wheel.symbol}')")

@cli.command()
@click.argument('symbol', required=False)
@click.option('--all', 'all_symbols', is_flag=True, help='All active wheels')
@click.pass_context
def recommend(ctx, symbol, all_symbols):
    """Get recommendation for next option to sell."""
    manager = ctx.obj['manager']

    if all_symbols:
        recs = manager.get_all_recommendations()
    elif symbol:
        recs = [manager.get_recommendation(symbol.upper())]
    else:
        click.echo("Error: Provide SYMBOL or --all")
        return

    for rec in recs:
        if rec:
            _print_recommendation(rec, ctx.obj['verbose'])

@cli.command()
@click.argument('symbol')
@click.argument('direction', type=click.Choice(['put', 'call']))
@click.option('--strike', required=True, type=float)
@click.option('--expiration', required=True, help='YYYY-MM-DD')
@click.option('--premium', required=True, type=float, help='Premium per share')
@click.option('--contracts', default=1, type=int)
@click.pass_context
def record(ctx, symbol, direction, strike, expiration, premium, contracts):
    """Record a sold option (collect premium)."""
    manager = ctx.obj['manager']
    trade = manager.record_trade(
        symbol=symbol.upper(),
        direction=direction,
        strike=strike,
        expiration_date=expiration,
        premium=premium,
        contracts=contracts,
    )
    click.echo(f"Recorded: SELL {contracts}x {symbol.upper()} ${strike} {direction.upper()}")
    click.echo(f"Premium collected: ${trade.total_premium:.2f} (${premium:.2f}/share)")
    click.echo(f"Expiration: {expiration}")

@cli.command()
@click.argument('symbol')
@click.option('--price', required=True, type=float, help='Stock price at expiration')
@click.pass_context
def expire(ctx, symbol, price):
    """Record expiration outcome (determines if assigned/exercised or expired worthless)."""
    manager = ctx.obj['manager']
    outcome = manager.record_expiration(symbol.upper(), price)

    wheel = manager.get_wheel(symbol.upper())

    if outcome == TradeOutcome.EXPIRED_WORTHLESS:
        click.echo(f"Option EXPIRED WORTHLESS - premium kept!")
    elif outcome == TradeOutcome.ASSIGNED:
        click.echo(f"PUT ASSIGNED - bought {wheel.shares_held} shares @ ${wheel.cost_basis:.2f}")
    elif outcome == TradeOutcome.CALLED_AWAY:
        click.echo(f"CALL EXERCISED - sold shares, received cash")

    click.echo(f"New state: {wheel.state.value}")

@cli.command()
@click.argument('symbol', required=False)
@click.option('--all', 'all_symbols', is_flag=True)
@click.pass_context
def status(ctx, symbol, all_symbols):
    """View current wheel status."""
    manager = ctx.obj['manager']

    if all_symbols:
        wheels = manager.list_wheels()
    elif symbol:
        wheel = manager.get_wheel(symbol.upper())
        wheels = [wheel] if wheel else []
    else:
        click.echo("Error: Provide SYMBOL or --all")
        return

    for wheel in wheels:
        _print_status(wheel, ctx.obj['verbose'])

@cli.command()
@click.argument('symbol', required=False)
@click.option('--all', 'all_symbols', is_flag=True)
@click.option('--export', type=click.Choice(['csv', 'json']), help='Export format')
@click.pass_context
def performance(ctx, symbol, all_symbols, export):
    """View performance metrics (premium collected, win rate, etc.)."""
    manager = ctx.obj['manager']

    if all_symbols:
        perf = manager.get_portfolio_performance()
    elif symbol:
        perf = manager.get_performance(symbol.upper())
    else:
        click.echo("Error: Provide SYMBOL or --all")
        return

    if export:
        data = manager.export_trades(symbol, format=export)
        click.echo(data)
    else:
        _print_performance(perf, ctx.obj['verbose'])

@cli.command()
@click.pass_context
def list(ctx):
    """List all wheel positions."""
    manager = ctx.obj['manager']
    wheels = manager.list_wheels()

    if not wheels:
        click.echo("No active wheels. Use 'wheel init SYMBOL --capital N' to start.")
        return

    click.echo(f"{'Symbol':<8} {'State':<20} {'Capital':>12} {'Shares':>8} {'Profile':<12}")
    click.echo("-" * 70)
    for w in wheels:
        click.echo(f"{w.symbol:<8} {w.state.value:<20} ${w.capital_allocated:>10,.2f} {w.shares_held:>8} {w.profile.value:<12}")
```

---

## 6. Integration Points

### 6.1 Existing Codebase Integration

| Component | Usage |
|-----------|-------|
| `StrikeOptimizer` | Strike selection, sigma calculations, P(ITM) |
| `CoveredCallAnalyzer` | Covered call analysis and metrics |
| `CoveredPutAnalyzer` | Cash-secured put analysis and metrics |
| `FinnhubClient` | Options chain data |
| `AlphaVantagePriceDataFetcher` | Current prices, historical data |
| `VolatilityCalculator` | Volatility estimation |
| `EarningsCalendar` | Earnings date warnings |
| `StrikeProfile` | Risk profile definitions |

---

## 7. Error Handling

### 7.1 Custom Exceptions

```python
# src/wheel/exceptions.py

class WheelError(Exception):
    """Base exception for wheel operations."""
    pass

class InvalidStateError(WheelError):
    """Operation not allowed in current state."""
    pass

class SymbolNotFoundError(WheelError):
    """Wheel position not found for symbol."""
    pass

class TradeNotFoundError(WheelError):
    """No open trade found."""
    pass
```

### 7.2 State Validation

| Operation | Required State | Error if Wrong State |
|-----------|---------------|---------------------|
| Sell Put | CASH | "Cannot sell put - not in CASH state" |
| Sell Call | SHARES | "Cannot sell call - no shares held" |
| Record Expiration | *_OPEN | "No open position to expire" |
| Get Recommendation | CASH or SHARES | "Has open position - wait for expiration" |

---

## 8. Testing Strategy

### 8.1 Unit Tests

```
tests/
  wheel/
    test_manager.py         # WheelManager operations
    test_recommend.py       # RecommendEngine bias logic
    test_performance.py     # Metrics calculations
    test_repository.py      # SQLite operations
    test_state.py           # State machine transitions
    test_cli.py             # CLI command parsing
```

### 8.2 Key Test Cases

| Test | Description |
|------|-------------|
| State transitions | All valid transitions work, invalid ones raise errors |
| Premium tracking | Premium accumulates correctly across trades |
| Assignment logic | Put assigned when price <= strike at expiry |
| Called away logic | Call exercised when price >= strike at expiry |
| Bias scoring | Further OTM options score higher |
| Multi-symbol | Can run independent wheels on different symbols |

---

## 9. Summary

The Wheel Strategy Tool provides a complete lifecycle management system for the options wheel strategy:

1. **Start with CASH** → Sell puts to collect premium
2. **If put expires OTM** → Keep premium, stay in CASH, sell more puts
3. **If put assigned** → Buy shares at strike, move to SHARES state
4. **In SHARES state** → Sell calls to collect premium
5. **If call expires OTM** → Keep premium, stay in SHARES, sell more calls
6. **If call exercised** → Sell shares at strike, move to CASH state
7. **Repeat** → Continuous premium collection cycle

The bias toward premium collection (vs. assignment) is achieved by:
- Selecting strikes further OTM within the chosen risk profile
- Preferring shorter-dated expirations
- Warning on high P(ITM) conditions
