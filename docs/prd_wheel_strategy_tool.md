# Product Requirements Document: Wheel Strategy Tool

## 1. Overview

### 1.1 Purpose

The Wheel Strategy Tool is a command-line utility and Python module for executing and tracking the options wheel strategy across multiple symbols. The tool emphasizes premium collection over assignment, using conservative strike selection and shorter expirations to minimize trading while maximizing income.

### 1.2 Background

The wheel strategy is a systematic approach to selling options:
1. **Cash-Secured Put (CSP)**: Sell OTM puts to collect premium. If assigned, acquire shares at a discount.
2. **Covered Call (CC)**: If holding shares, sell OTM calls to collect premium. If called away, profit from premium + capital gains.
3. **Repeat**: Cycle continues indefinitely, generating income in both directions.

### 1.3 Goals

- Provide a unified tool for managing wheel strategy positions across multiple symbols
- Bias toward premium collection (letting options expire worthless) over assignment
- Track performance with actual expiration outcomes to measure strategy effectiveness
- Support both CLI usage and programmatic module access
- Integrate with existing options_income infrastructure

### 1.4 Non-Goals

- Automated order execution (recommendations only)
- Tax lot tracking or wash sale detection
- Push notifications or alerts
- Intraday tick-by-tick monitoring

---

## 2. User Stories

### 2.1 Primary User Stories

**US-1: Initialize a New Wheel**
> As a trader, I want to start a new wheel position on a symbol with my desired capital allocation so that I can begin collecting premium.

**US-2: Get Next Recommendation**
> As a trader, I want to see the recommended option to sell (put or call) based on my current position and risk profile so that I can execute the trade manually.

**US-3: Record a Trade**
> As a trader, I want to record the option I sold (strike, expiration, premium) so that the tool can track my position and performance.

**US-4: Check Expiration Outcome**
> As a trader, I want to record the stock price at expiration so the tool can determine if my option was assigned and update my position accordingly.

**US-5: View Performance**
> As a trader, I want to see my cumulative premium collected, win rate, and P&L across all wheel positions so that I can evaluate strategy effectiveness.

**US-6: Manage Multiple Wheels**
> As a trader, I want to run wheels on multiple symbols simultaneously so that I can diversify my premium income.

### 2.2 Secondary User Stories

**US-7: Import Existing Position**
> As a trader, I want to import an existing stock position into the wheel tracker so that I can start writing calls against shares I already own.

**US-8: Export Trade History**
> As a trader, I want to export my trade history to CSV for external analysis or tax preparation.

**US-9: Adjust Risk Profile**
> As a trader, I want to change my aggressiveness level mid-cycle so that I can adapt to changing market conditions.

**US-10: Monitor Open Positions**
> As a trader, I want to see current market data for my open positions (days to expiration, current price vs strike, ITM/OTM status) so that I can assess assignment risk without manual price lookups.

**US-11: Track Position Evolution**
> As a trader, I want to see how my position moneyness has changed over time so that I can understand price movement patterns and refine my strike selection strategy.

**US-12: Identify High-Risk Positions**
> As a trader, I want to be alerted when a position moves ITM so that I can decide whether to close it early or prepare for assignment.

---

## 3. Functional Requirements

### 3.1 Configuration Management

**FR-1: Capital Configuration**
- Accept initial capital in dollars for cash-secured put sizing
- Calculate maximum contracts based on capital and strike price
- Track available vs. deployed capital per symbol

**FR-2: Share Configuration**
- Accept existing share count for covered call sizing
- Track share inventory per symbol (0, 100, 200, etc.)
- Update shares on assignment/call-away events

**FR-3: Starting Direction**
- Accept optional starting direction: "put" or "call"
- Default to "put" if no shares held
- Default to "call" if shares already held
- Allow override for strategic entry points

**FR-4: Aggressiveness Profile**
- Support four profiles: aggressive, moderate, conservative, defensive
- Map profiles to sigma ranges (existing StrikeProfile enum):
  - Aggressive: 0.5-1.0σ OTM
  - Moderate: 1.0-1.5σ OTM
  - Conservative: 1.5-2.0σ OTM
  - Defensive: 2.0-2.5σ OTM
- Profile affects both put and call strike selection

### 3.2 Premium Collection Bias

**FR-5: Strike Selection Bias**
- Prefer strikes further OTM than the profile midpoint
- Within profile range, select strike closest to upper sigma bound
- Example: Conservative (1.5-2.0σ) → prefer strikes near 2.0σ

**FR-6: Expiration Selection Bias**
- Prefer shorter-dated expirations (weekly over monthly)
- Default to nearest weekly expiration with adequate liquidity
- Allow override for specific expiration dates

**FR-7: Anti-Assignment Warnings**
- Warn when selected strike has P(ITM) > profile threshold
- Warn when earnings fall before expiration
- Warn when ex-dividend date falls before expiration

### 3.3 Position Tracking

**FR-8: Wheel State Machine**
Each wheel position has a state:
- `IDLE`: No position, ready to sell puts
- `PUT_OPEN`: Cash-secured put sold, awaiting expiration
- `HOLDING_SHARES`: Shares acquired via assignment, ready to sell calls
- `CALL_OPEN`: Covered call sold, awaiting expiration

**FR-9: Trade Recording**
Record for each trade:
- Symbol, direction (put/call), strike, expiration date
- Premium received (per share and total)
- Contracts sold
- Open date, close date
- Outcome: expired_worthless, assigned, called_away, closed_early

**FR-10: Expiration Recording**
Record at expiration:
- Stock price at market close on expiration day
- Whether option finished ITM or OTM
- Assignment/exercise status
- Position state transition

### 3.4 Performance Tracking

**FR-11: Premium Metrics**
- Total premium collected (lifetime and per symbol)
- Premium per cycle (put→call→repeat)
- Average premium yield (annualized)

**FR-12: Outcome Metrics**
- Win rate: % of options expiring worthless
- Assignment rate: % of puts assigned
- Call-away rate: % of calls exercised
- Average days in position

**FR-13: P&L Metrics**
- Realized P&L from premium
- Unrealized P&L from share positions
- Total return on capital deployed

### 3.5 Multi-Symbol Support

**FR-14: Portfolio View**
- List all active wheel positions
- Show state, current option, days to expiration
- Aggregate metrics across portfolio

**FR-15: Symbol Isolation**
- Each symbol tracked independently
- Separate capital allocation per symbol
- No cross-symbol dependencies

### 3.6 Data Integration

**FR-16: Live Data**
- Fetch options chains from Finnhub API
- Fetch current prices from Schwab API with Alpha Vantage fallback
- Use existing codebase clients and caching (5-minute TTL)

**FR-17: Volatility Calculation**
- Use existing VolatilityCalculator for sigma calculations
- Apply blended volatility for strike selection
- Cache volatility data per session

### 3.7 Position Monitoring

**FR-18: Days to Expiration (DTE) Display**
- Calculate calendar days remaining until expiration
- Calculate trading days remaining (exclude weekends and holidays)
- Display format: "14 days (10 trading days)"
- Update automatically when viewing position status

**FR-19: Moneyness Calculation**
- Determine if position is In-The-Money (ITM) or Out-of-The-Money (OTM)
- For puts: ITM when current price ≤ strike
- For calls: ITM when current price ≥ strike
- Calculate percentage distance from strike
- Display format: "OTM by 2.3%" or "ITM by 1.8%"

**FR-20: Risk Assessment**
- Assign risk levels based on moneyness:
  - LOW: OTM by >5% (comfortable safety margin)
  - MEDIUM: OTM by 0-5% (approaching strike, danger zone)
  - HIGH: ITM by any amount (assignment/exercise risk present)
- Display risk level prominently in status views
- Highlight HIGH risk positions with visual warnings

**FR-21: Position Refresh Timing**
- On startup: Refresh all open positions once
- During market hours: Refresh positions every hour automatically
- After market close: Refresh once at 4:15 PM ET to capture closing prices
- Manual refresh: Allow user to force fresh data fetch via --refresh flag
- Respect existing 5-minute cache TTL to minimize API calls

**FR-22: Historical Snapshot Tracking**
- Create daily snapshots of position status
- Record: date, price, DTE, moneyness percentage, ITM status, risk level
- Store snapshots in database for trend analysis
- Enable comparison of position evolution over time
- Run snapshot creation after market close (via scheduled command)

**FR-23: Status Display Enhancement**
- Show live market data for all open positions
- Include: current price, DTE, moneyness, risk level in status output
- Provide both summary view (list all) and detailed view (single position)
- Timestamp all live data displays
- Highlight positions requiring attention (ITM/high risk)

---

## 4. Command-Line Interface

### 4.1 Commands

```bash
# Initialize a new wheel
wheel init SYMBOL --capital 10000 --profile conservative

# Import existing shares
wheel import SYMBOL --shares 200 --cost-basis 150.00

# Get next recommendation
wheel recommend SYMBOL
wheel recommend --all  # All active symbols

# Record a trade
wheel record SYMBOL put --strike 145 --expiration 2025-02-21 --premium 1.50 --contracts 1

# Record expiration outcome
wheel expire SYMBOL --price 148.50

# View status (with live monitoring data)
wheel status SYMBOL
wheel status --all
wheel status SYMBOL --refresh  # Force fresh data

# View performance
wheel performance SYMBOL
wheel performance --all --export csv

# List all wheels (with live monitoring data)
wheel list
wheel list --refresh  # Force fresh data

# Refresh position snapshots (create daily historical records)
wheel refresh

# Close/archive a wheel
wheel close SYMBOL
```

### 4.2 Global Options

```bash
--profile {aggressive,moderate,conservative,defensive}  # Risk profile
--db PATH          # Database file path (default: ~/.wheel_strategy/trades.db)
--config PATH      # Config file path
--verbose / -v     # Verbose output
--json             # Output as JSON (for scripting)
```

### 4.3 Configuration File

Support YAML configuration file (`~/.wheel_strategy/config.yaml`):

```yaml
default_profile: conservative
default_capital: 10000
symbols:
  AAPL:
    capital: 15000
    profile: moderate
  NVDA:
    capital: 20000
    profile: conservative
api_keys:
  finnhub: ${FINNHUB_API_KEY}
  alpha_vantage: ${ALPHA_VANTAGE_API_KEY}
```

---

## 5. Module API

### 5.1 Core Classes

Module provides WheelManager for all operations:
- Wheel lifecycle (create, import, list, close)
- Recommendations (get next option to sell)
- Trade recording (record sales and expirations)
- Performance tracking (metrics and analytics)
- Position monitoring (live status and snapshots)

Key operations:
- Initialize manager with database path
- Create wheels with capital and profile
- Get recommendations based on current state
- Record trades and expiration outcomes
- Monitor open positions with live data
- Get performance metrics
- Create historical snapshots

### 5.2 Data Classes

**WheelPosition**: Represents a wheel strategy position on a symbol
- Symbol, state, capital, shares, cost basis, profile
- Tracks whether position is in CASH or SHARES state
- Indicates if open position exists (awaiting expiration)

**TradeRecord**: Records a single option trade (put or call sold)
- Symbol, direction, strike, expiration, premium, contracts
- Open/close timestamps
- Outcome (open, expired_worthless, assigned, called_away)
- Price at expiration for assignment determination

**WheelPerformance**: Performance metrics for a wheel position
- Total premium collected, trade counts, win rates
- Assignment and called-away event counts
- Average holding period, annualized yield
- Realized P&L

**PositionStatus**: Live monitoring data for an open position
- Current price, DTE (calendar and trading days)
- Moneyness (ITM/OTM status and percentage)
- Risk level (LOW/MEDIUM/HIGH) with visual indicator
- Price vs strike comparison
- Last update timestamp

**PositionSnapshot**: Historical daily snapshot of position status
- Trade reference, snapshot date
- Price, DTE, moneyness at snapshot time
- ITM status and risk level at snapshot time
- Enables trend analysis over position lifetime

---

## 6. Database Schema

### 6.1 Tables

**wheels**
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment ID |
| symbol | TEXT | Stock symbol |
| state | TEXT | Current state (IDLE, PUT_OPEN, etc.) |
| capital_allocated | REAL | Capital for this wheel |
| shares_held | INTEGER | Current share count |
| cost_basis | REAL | Average cost per share |
| profile | TEXT | Risk profile |
| created_at | TEXT | ISO timestamp |
| updated_at | TEXT | ISO timestamp |
| is_active | INTEGER | 1=active, 0=archived |

**trades**
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment ID |
| wheel_id | INTEGER FK | Reference to wheels.id |
| symbol | TEXT | Stock symbol |
| direction | TEXT | "put" or "call" |
| strike | REAL | Strike price |
| expiration_date | TEXT | YYYY-MM-DD |
| premium_per_share | REAL | Premium received per share |
| contracts | INTEGER | Number of contracts |
| total_premium | REAL | Total premium received |
| opened_at | TEXT | ISO timestamp |
| closed_at | TEXT | ISO timestamp (nullable) |
| outcome | TEXT | expired_worthless, assigned, called_away, closed_early |
| price_at_expiry | REAL | Stock price at expiration (nullable) |

**position_snapshots** (daily position monitoring history)
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment ID |
| trade_id | INTEGER FK | Reference to trades.id |
| snapshot_date | TEXT | YYYY-MM-DD |
| current_price | REAL | Stock price at snapshot time |
| dte_calendar | INTEGER | Calendar days to expiration |
| dte_trading | INTEGER | Trading days to expiration |
| moneyness_pct | REAL | Percentage distance from strike |
| is_itm | INTEGER | 1=ITM, 0=OTM |
| risk_level | TEXT | LOW, MEDIUM, or HIGH |
| created_at | TEXT | ISO timestamp |

---

## 7. Acceptance Criteria

### 7.1 Core Functionality

| ID | Criteria | Verification |
|----|----------|--------------|
| AC-1 | Can initialize a wheel with capital and profile | CLI: `wheel init AAPL --capital 10000` succeeds |
| AC-2 | Can import existing shares | CLI: `wheel import AAPL --shares 100` creates HOLDING_SHARES state |
| AC-3 | Recommendations respect profile sigma range | Output strike within profile bounds |
| AC-4 | Recommendations bias toward further OTM | Selected strike ≥ profile midpoint sigma |
| AC-5 | Recommendations prefer weekly expirations | Default to nearest weekly when available |
| AC-6 | Can record put and call trades | Trade persisted to database |
| AC-7 | Can record expiration outcome | State transitions correctly on assignment |
| AC-8 | Performance metrics calculate correctly | Win rate = worthless / total trades |
| AC-9 | Multi-symbol tracking works | Can run 3+ concurrent wheels |
| AC-10 | Module API matches CLI functionality | All CLI commands have API equivalents |

### 7.2 Premium Bias

| ID | Criteria | Verification |
|----|----------|--------------|
| AC-11 | Conservative profile selects ~2σ strikes | Strike sigma distance ≥ 1.75σ |
| AC-12 | Warns on high P(ITM) selections | Warning if P(ITM) > 15% for conservative |
| AC-13 | Warns on earnings conflicts | Warning if earnings before expiration |
| AC-14 | Prefers shorter DTE | Selects weekly over monthly by default |

### 7.3 Data Integrity

| ID | Criteria | Verification |
|----|----------|--------------|
| AC-15 | State machine enforced | Cannot sell call without shares |
| AC-16 | Trade history immutable | Recorded trades cannot be modified |
| AC-17 | Database survives restarts | Data persists across sessions |
| AC-18 | Export produces valid CSV | Exported data importable to spreadsheet |

### 7.4 Position Monitoring

| ID | Criteria | Verification |
|----|----------|--------------|
| AC-19 | DTE displays both calendar and trading days | Format: "14 days (10 trading days)" |
| AC-20 | Moneyness calculated correctly for puts | ITM when price ≤ strike, OTM when price > strike |
| AC-21 | Moneyness calculated correctly for calls | ITM when price ≥ strike, OTM when price < strike |
| AC-22 | Risk level HIGH for any ITM position | Any intrinsic value triggers HIGH risk |
| AC-23 | Risk level MEDIUM for near-money positions | OTM by 0-5% shows MEDIUM risk |
| AC-24 | Risk level LOW for safe positions | OTM by >5% shows LOW risk |
| AC-25 | Status command shows live data | Current price, DTE, moneyness, risk displayed |
| AC-26 | List command shows monitoring for all positions | Table includes DTE and risk columns |
| AC-27 | Refresh respects cache timing | No API calls if data < 5 minutes old (unless --refresh) |
| AC-28 | Daily snapshots created | One snapshot per position per day |
| AC-29 | Snapshots stored with unique constraint | Cannot create duplicate for same trade+date |
| AC-30 | HIGH risk positions visually highlighted | Warning displayed for ITM positions |

---

## 8. Future Enhancements (Out of Scope)

- Broker API integration for automated execution
- Real-time position monitoring with alerts
- Tax lot tracking and wash sale detection
- Backtesting against historical data
- Web dashboard for visualization
- Mobile notifications for expirations

---

## 9. Dependencies

### 9.1 Existing Codebase

- `src/strike_optimizer.py`: Strike selection and probability calculations
- `src/covered_strategies.py`: CoveredCallAnalyzer, CoveredPutAnalyzer, WheelStrategy
- `src/finnhub_client.py`: Options chain data
- `src/price_fetcher.py`: Current price data
- `src/volatility.py`: Volatility calculations
- `src/models/profiles.py`: StrikeProfile enum

### 9.2 External Libraries

- `sqlite3`: Database (standard library)
- `click` or `argparse`: CLI framework
- `pyyaml`: Configuration file parsing
- Existing API clients (Finnhub, Alpha Vantage)

---

## 10. Glossary

| Term | Definition |
|------|------------|
| **Wheel Strategy** | Systematic approach alternating between selling puts and calls |
| **CSP** | Cash-Secured Put - selling a put backed by cash to buy shares |
| **CC** | Covered Call - selling a call against shares you own |
| **Assignment** | Put seller obligated to buy shares at strike price |
| **Called Away** | Call seller obligated to sell shares at strike price |
| **Premium** | Income received from selling an option |
| **OTM** | Out of the Money - strike price away from current price |
| **P(ITM)** | Probability of finishing In the Money at expiration |
| **DTE** | Days to Expiration |
