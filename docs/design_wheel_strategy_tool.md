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
│  - Monitoring    │                  │                           │
└──────────────────┴──────────────────┴───────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Monitoring Components                       │
├──────────────────┬──────────────────┬───────────────────────────┤
│  PositionMonitor │  PositionStatus  │  PositionSnapshot         │
│  - Live data     │  - DTE tracking  │  - Daily snapshots        │
│  - Moneyness     │  - Risk levels   │  - Historical trends      │
│  - Risk assess   │  - ITM/OTM calc  │  - Time series data       │
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
| WheelManager | Orchestrate operations, enforce state machine, coordinate monitoring |
| RecommendEngine | Generate biased strike recommendations |
| PerformanceTracker | Calculate and aggregate metrics |
| PositionMonitor | Track open positions, calculate live status, assess risk |
| WheelRepository | SQLite persistence, queries, snapshot storage |
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
    monitor.py                  # PositionMonitor class (NEW)
    repository.py               # WheelRepository (SQLite)
    models.py                   # Data classes (WheelPosition, TradeRecord, PositionStatus, etc.)
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



### 4.3 PositionMonitor

**Purpose**: Monitor open wheel positions and provide real-time status updates.

**Responsibilities**:
- Fetch current prices for symbols with open positions
- Calculate days to expiration (calendar and trading days)
- Determine moneyness (ITM/OTM status and percentage)
- Assess assignment risk and assign risk levels
- Create daily snapshots for historical tracking
- Integrate with existing price fetching infrastructure
- Respect caching (5-minute TTL) to minimize API calls

**Key Operations**:
- `get_position_status()`: Calculate current status for a single open position
- `get_all_positions_status()`: Batch status calculation for all open positions
- `create_snapshot()`: Generate daily historical snapshot
- `_calculate_moneyness()`: Determine ITM/OTM and percentage distance
- `_assess_risk()`: Assign LOW/MEDIUM/HIGH risk level based on moneyness
- `_fetch_current_price()`: Get latest price (respects cache)

**Moneyness Logic**:
- For puts: ITM when current_price ≤ strike
- For calls: ITM when current_price ≥ strike
- Percentage calculated as distance from strike / strike * 100
- Display format: "OTM by 2.3%" or "ITM by 1.8%"

**Risk Assessment Rules**:
- HIGH (🔴): Any ITM position (assignment/exercise risk present)
- MEDIUM (🟡): OTM by 0-5% (danger zone, approaching strike)
- LOW (🟢): OTM by >5% (comfortable safety margin)

**Integration Points**:
- Uses SchwabClient for price data (primary)
- Falls back to AlphaVantagePriceDataFetcher
- Leverages existing calculate_days_to_expiry utility
- Respects existing 5-minute quote cache



**Position Monitoring Operations**:

WheelManager coordinates position monitoring through integration with PositionMonitor:
- Get current status for a specific symbol's open position
- Get status for all open positions across portfolio
- Force refresh to bypass cache and fetch fresh data
- Create daily snapshots for historical tracking
- Check if snapshots already exist for current date

Monitoring operations respect the existing 5-minute cache TTL and only fetch fresh data when necessary or explicitly requested.

---

## 5. CLI Implementation

### 5.1 Enhanced Commands for Position Monitoring

**status command** - Enhanced with live monitoring data:
- Displays current price, DTE (calendar and trading days), moneyness percentage
- Shows risk level (LOW/MEDIUM/HIGH) with visual indicators
- Highlights HIGH risk positions (ITM) with warnings
- Accepts --refresh flag to force fresh data fetch
- Works for single symbol or all positions (--all)

**list command** - Enhanced with monitoring columns:
- Table includes: Symbol, State, Strike, Current Price, DTE, Moneyness, Risk
- Shows live data for all open positions in a single view
- Closed positions show placeholder values
- Summary line shows count of HIGH risk positions
- Accepts --refresh flag

**refresh command** (NEW):
- Creates daily snapshots for all open positions
- Checks if snapshots already exist for today (prevents duplicates)
- Fetches fresh market data
- Reports count of snapshots created
- Intended for scheduled execution (cron) after market close



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

## 8. Refresh Strategy

### 8.1 Timing Requirements

Based on stakeholder requirements, position data is refreshed according to the following schedule:

**On Startup**: When the CLI tool is invoked, all open positions are refreshed once to ensure current data. Respects 5-minute cache if data is recent.

**Hourly During Market Hours**: While the tool is running, positions are refreshed every hour during market hours (9:30 AM - 4:00 PM ET). This provides regular updates without excessive API calls.

**After Market Close**: A single refresh occurs at 4:15 PM ET to capture final closing prices. This ensures end-of-day accuracy for positions.

**Manual Refresh**: Users can force a fresh data fetch using the --refresh flag on status and list commands, bypassing the cache.

**Daily Snapshots**: The refresh command creates historical snapshots, intended to run once daily via cron job after market close.

### 8.2 Implementation Approach

The tool uses a **CLI-managed approach** rather than a background daemon:
- Each command respects cache timestamps (5-minute TTL)
- Users trigger refreshes explicitly via --refresh flag
- Daily snapshot creation runs via user's cron job
- No persistent background process required
- Aligns with CLI tool philosophy (manual check-ins)

### 8.3 Cron Job Configuration

Users configure their system cron to handle scheduled refreshes:

**Daily snapshot after market close** (4:15 PM ET weekdays):
- Creates historical snapshots for trend analysis
- Captures closing prices for all open positions

**Optional morning check** (before market open):
- Provides pre-market status review
- Helps plan intraday management actions

### 8.4 Cache Management

The monitoring system integrates with existing caching infrastructure:
- 5-minute TTL on price quotes (existing)
- Internal cache in PositionMonitor for additional efficiency
- force_refresh parameter bypasses all caches
- Cache respects market hours (no stale after-hours data)

---

## 9. Testing Strategy

### 9.1 Unit Tests

Test files organized by component:
- test_manager.py: WheelManager operations including monitoring coordination
- test_recommend.py: RecommendEngine bias logic and strike selection
- test_performance.py: Metrics calculations and aggregation
- test_monitor.py: PositionMonitor operations (NEW)
- test_repository.py: SQLite operations including snapshot persistence
- test_state.py: State machine transitions
- test_cli.py: CLI command parsing including enhanced status/list commands

### 9.2 Key Test Cases

| Test | Description |
|------|-------------|
| State transitions | All valid transitions work, invalid ones raise errors |
| Premium tracking | Premium accumulates correctly across trades |
| Assignment logic | Put assigned when price <= strike at expiry |
| Called away logic | Call exercised when price >= strike at expiry |
| Bias scoring | Further OTM options score higher |
| Multi-symbol | Can run independent wheels on different symbols |
| Moneyness - Put ITM | current_price <= strike correctly identified as ITM |
| Moneyness - Put OTM | current_price > strike correctly identified as OTM |
| Moneyness - Call ITM | current_price >= strike correctly identified as ITM |
| Moneyness - Call OTM | current_price < strike correctly identified as OTM |
| Risk - HIGH | Any ITM position triggers HIGH risk |
| Risk - MEDIUM | OTM by 0-5% triggers MEDIUM risk |
| Risk - LOW | OTM by >5% triggers LOW risk |
| DTE calculation | Both calendar and trading days calculated correctly |
| Cache respect | Status check within 5 min uses cached data |
| Force refresh | --refresh flag bypasses cache |
| Daily snapshots | One snapshot per position per day, no duplicates |
| Snapshot storage | Snapshots persist correctly with unique constraint |
| Status display | Live monitoring data shown for open positions |
| List display | All positions shown with monitoring columns |

---

## 10. Summary

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

**Position Monitoring** enhances the tool with real-time visibility:
- Live tracking of days to expiration (calendar and trading days)
- Automatic moneyness calculation (ITM/OTM status with percentage distance)
- Risk assessment (LOW/MEDIUM/HIGH) based on assignment likelihood
- Visual warnings for positions requiring attention (ITM = assignment risk)
- Historical snapshot tracking for trend analysis
- Integration with existing price fetching and caching infrastructure
