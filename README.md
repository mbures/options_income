# Options Income Strategy Optimization System

A Python-based system for optimizing covered call and cash-secured put strategies. Provides volatility analysis, strike optimization, risk metrics, and automated position recommendations.

## Features

### Core Capabilities

- **Volatility Engine**: Multiple volatility models (Close-to-Close, Parkinson, Garman-Klass, Yang-Zhang) with configurable blending
- **Strike Optimization**: Sigma-based strike selection with probability calculations using Black-Scholes
- **Covered Strategies**: Full analysis for covered calls, cash-secured puts, and wheel strategy
- **Risk Analysis**: Expected value, opportunity cost, risk-adjusted returns, scenario modeling
- **Weekly Overlay Scanner**: Automated recommendations with delta-band selection and tradability filters
- **Ladder Builder**: Multi-week position allocation across weekly expirations

### Data Sources

- **Schwab API** (PRIMARY): Historical price data, options chains, account data, positions via OAuth 2.0
- **Finnhub** (OPTIONAL): Earnings calendar only (free tier)

### Schwab Integration

The system uses **Charles Schwab** as the primary data source with OAuth 2.0 authentication. This provides:

- **Historical price data** (OHLCV data via /marketdata/v1/pricehistory)
- **Real-time market data** (quotes, options chains)
- **Account access** (positions, balances)
- **Automated trading** (coming soon)
- **Token auto-refresh** (seamless 7-day authorization)

#### Setup Required

1. **Get Schwab Developer credentials**: [https://developer.schwab.com](https://developer.schwab.com)
2. **Configure OAuth**: See [docs/SCHWAB_OAUTH_SETUP.md](docs/SCHWAB_OAUTH_SETUP.md) for detailed setup
3. **Authorize** (one-time, on host machine):
   ```bash
   python scripts/authorize_schwab_host.py
   ```
4. **Use the wheel CLI**:
   ```bash
   python -m src.wheel.cli status
   python -m src.wheel.cli recommend AAPL
   ```

For complete setup instructions including SSL certificates, port forwarding, and container architecture, see the [Schwab OAuth Setup Guide](docs/SCHWAB_OAUTH_SETUP.md).

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up Schwab OAuth (Required)

Follow the [Schwab OAuth Setup Guide](docs/SCHWAB_OAUTH_SETUP.md) to:
- Register your app at developer.schwab.com
- Configure OAuth credentials
- Run authorization flow

### 3. Optional: Set Finnhub API Key (for Earnings Calendar)

```bash
export FINNHUB_API_KEY="your_finnhub_key"
```

Or create a `.env` file:
```
FINNHUB_API_KEY=your_finnhub_key
```

### 4. Run Wheel Strategy CLI

The CLI supports two modes of operation:

**Direct Mode (Default)**: CLI accesses database directly
```bash
# Initialize a new wheel position
python -m src.wheel.cli init AAPL --capital 15000

# Get recommendations
python -m src.wheel.cli recommend AAPL

# View status
python -m src.wheel.cli status AAPL
```

**API Mode (NEW)**: CLI communicates with API server
```bash
# Start API server first (in another terminal)
uvicorn src.server.main:app --port 8000

# Configure API mode
export WHEEL_API_URL="http://localhost:8000"

# Use CLI in API mode (with portfolio support)
python -m src.wheel.cli --api-mode portfolio create "Main Portfolio"
python -m src.wheel.cli --api-mode init AAPL --capital 15000
python -m src.wheel.cli --api-mode list --refresh
```

For complete CLI API mode documentation, see [CLI API Mode Guide](docs/CLI_API_MODE_GUIDE.md).

### 5. Run FastAPI Backend Server (NEW)

The system now includes a FastAPI backend server for RESTful API access to wheel strategy functionality.

**Start the server:**
```bash
# Development mode with auto-reload
uvicorn src.server.main:app --reload --port 8000

# Or run directly
python -m src.server.main
```

**Access the API:**
- Health check: http://localhost:8000/health
- System info: http://localhost:8000/api/v1/info
- Interactive API docs: http://localhost:8000/docs
- ReDoc documentation: http://localhost:8000/redoc
- OpenAPI schema: http://localhost:8000/openapi.json

**Configuration:**
The server can be configured using environment variables with `WHEEL_` prefix:
```bash
export WHEEL_DEBUG=true
export WHEEL_DATABASE_PATH=~/.wheel_strategy/trades.db
export WHEEL_HOST=0.0.0.0
export WHEEL_PORT=8000
```

**CORS Configuration:**
By default, the server allows requests from:
- http://localhost:3000
- http://localhost:8080
- http://127.0.0.1:3000
- http://127.0.0.1:8080

**Database Migrations:**
The server uses Alembic for database migrations:
```bash
# View current migration status
alembic current

# View migration history
alembic history

# Apply migrations (when available)
alembic upgrade head

# Rollback one version
alembic downgrade -1
```

## Sample Programs

### example_end_to_end.py

**Purpose:** Demonstrates the complete options analysis pipeline with live data from free API tiers.

**What It Does:**
- Fetches historical price data (Alpha Vantage TIME_SERIES_DAILY)
- Retrieves options chains (Finnhub free tier)
- Calculates multiple volatility models (Close-to-Close, Parkinson, Garman-Klass, Yang-Zhang)
- Performs volatility blending and regime analysis
- Demonstrates strike optimization with sigma-based calculations
- Analyzes covered calls, cash-secured puts, and wheel strategy
- Runs weekly overlay scanner on portfolio holdings
- Builds multi-week ladder positions

**Arguments:** None (edit symbol in source to change ticker)

**Sample Usage:**
```bash
# Run the complete demonstration
python example_end_to_end.py

# Output includes:
# - Historical price data fetch with API usage tracking
# - Realized volatility calculations (30/60 days, multiple models)
# - Implied volatility extraction from options chain
# - Blended volatility with regime analysis
# - Strike recommendations at various sigma levels
# - Covered call/put analysis with risk metrics
# - Weekly overlay scanner recommendations
# - Multi-week ladder position allocation
```

**Prerequisites:**
- Environment variables: `FINNHUB_API_KEY`, `ALPHA_VANTAGE_API_KEY`
- Or `.env` file with API keys

---

### wheel_strategy_tool.py

**Purpose:** Production-ready CLI tool for managing wheel strategy positions across multiple symbols.

**What It Does:**
- Tracks wheel positions through full lifecycle (cash → puts → shares → calls → cash)
- Provides real-time recommendations for next option to sell
- Calculates optimal strikes using volatility and risk profiles
- Records all trades with premium tracking
- Monitors performance metrics (realized gains, unrealized P&L, total returns)
- Maintains SQLite database for position persistence

**Commands:**

| Command | Description |
|---------|-------------|
| `init` | Initialize new wheel position with capital and/or shares |
| `recommend` | Get recommendation for next option to sell |
| `record` | Record a sold option and collect premium |
| `expire` | Record expiration outcome (expired/assigned) |
| `close` | Close an open trade early (buy back option) |
| `status` | View current wheel status and open positions |
| `history` | View complete trade history for a symbol |
| `performance` | View detailed performance metrics |
| `list` | List all active wheel positions |
| `archive` | Archive/close a completed wheel position |
| `update` | Update wheel settings (capital, risk profile) |

**Arguments:**

**Global Options:**
- `--db TEXT` - Database file path (default: `wheel_positions.db`)
- `-v, --verbose` - Verbose output with detailed logging
- `--json` - JSON output format (where supported)

**Sample Usage:**

```bash
# Initialize a new wheel position with cash (to sell puts)
python wheel_strategy_tool.py init AAPL --capital 15000

# Initialize with existing shares (to sell calls)
python wheel_strategy_tool.py init NVDA --shares 200 --cost-basis 150

# Initialize with both cash and shares
python wheel_strategy_tool.py init TSLA --capital 10000 --shares 100 --cost-basis 245

# Get recommendation for specific symbol
python wheel_strategy_tool.py recommend AAPL

# Get recommendations for all active wheels
python wheel_strategy_tool.py recommend --all

# Record a sold put option
python wheel_strategy_tool.py record AAPL put \
  --strike 150 \
  --expiration 2026-02-21 \
  --premium 2.50 \
  --contracts 1

# Record a sold covered call
python wheel_strategy_tool.py record NVDA call \
  --strike 200 \
  --expiration 2026-02-21 \
  --premium 3.75 \
  --contracts 2

# Record expiration outcome
python wheel_strategy_tool.py expire AAPL --strike 150 --expiry 2026-02-21 --expired

# Close trade early (buy back option)
python wheel_strategy_tool.py close AAPL \
  --strike 150 \
  --expiry 2026-02-21 \
  --close-premium 0.50

# View current status
python wheel_strategy_tool.py status AAPL

# View all active wheels
python wheel_strategy_tool.py status --all

# View trade history
python wheel_strategy_tool.py history AAPL

# View performance metrics
python wheel_strategy_tool.py performance AAPL

# List all positions
python wheel_strategy_tool.py list

# Archive completed wheel
python wheel_strategy_tool.py archive AAPL
```

**Risk Profiles:**
- `aggressive` - Higher premiums, more assignment risk (0.5-1.0σ, 30-40% ITM probability)
- `moderate` - Balanced approach (1.0-1.5σ, 15-30% ITM probability)
- `conservative` - Lower risk, steady income (1.5-2.0σ, 7-15% ITM probability)
- `defensive` - Maximum protection (2.0-2.5σ, 2-7% ITM probability)

**Database:**
- SQLite database stores all positions, trades, and history
- Default location: `wheel_positions.db` in current directory
- Portable - can be backed up or moved between systems

---

## Usage Examples

### Volatility Analysis

```python
from src.volatility import VolatilityCalculator
from src.price_fetcher import AlphaVantagePriceDataFetcher

fetcher = AlphaVantagePriceDataFetcher(config)
price_data = fetcher.fetch_price_data("AAPL", days=100)

calculator = VolatilityCalculator(price_data)
volatility = calculator.calculate_blended_volatility()
print(f"30-day blended volatility: {volatility:.2%}")
```

### Strike Optimization

```python
from src.strike_optimizer import StrikeOptimizer, StrikeProfile

optimizer = StrikeOptimizer()

# Get strike at 1.5 sigma for covered call
result = optimizer.calculate_strike_at_sigma(
    current_price=100.0,
    volatility=0.25,
    days_to_expiry=30,
    sigma=1.5,
    option_type="call"
)
print(f"1.5σ call strike: ${result.theoretical_strike:.2f}")
print(f"Tradeable strike: ${result.tradeable_strike:.2f}")

# Get ranked recommendations
recommendations = optimizer.get_strike_recommendations(
    options_chain=chain,
    current_price=100.0,
    volatility=0.25,
    days_to_expiry=30,
    profile=StrikeProfile.CONSERVATIVE
)
```

### Covered Call Analysis

```python
from src.covered_strategies import CoveredCallAnalyzer

analyzer = CoveredCallAnalyzer(strike_optimizer)
result = analyzer.analyze(
    contract=call_option,
    current_price=185.50,
    volatility=0.30,
    shares=100
)

print(f"Premium: ${result.total_premium:.2f}")
print(f"Max profit if called: ${result.max_profit:.2f}")
print(f"Annualized return: {result.annualized_return_if_flat*100:.1f}%")
```

### Risk Analysis

```python
from src.risk_analyzer import RiskAnalyzer

analyzer = RiskAnalyzer()
analysis = analyzer.analyze_covered_call(
    current_price=100.0,
    strike=105.0,
    premium=2.50,
    days_to_expiry=30,
    probability_itm=0.25
)

print(f"Expected value: ${analysis.risk_metrics.expected_value:.2f}")
print(f"Opportunity cost: ${analysis.risk_metrics.opportunity_cost:.2f}")
print(f"Annualized yield: {analysis.income_metrics.annualized_yield_pct:.1f}%")
```

### Weekly Overlay Scanner

```python
from src.overlay_scanner import OverlayScanner, ScannerConfig
from src.models import PortfolioHolding, DeltaBand

config = ScannerConfig(
    overwrite_cap_pct=25.0,
    delta_band=DeltaBand.CONSERVATIVE
)

scanner = OverlayScanner(finnhub_client, strike_optimizer, config)
holdings = [PortfolioHolding(symbol="AAPL", shares=500)]

results = scanner.scan_portfolio(holdings, options_chains)
for result in results:
    print(f"{result.symbol}: {len(result.recommended_strikes)} recommendations")
```

### Charles Schwab API Integration
Integration requires creating an app on their platform. This system generates API keys that are then used to make calls to their API. The process of claiming these API keys(which expire) is OAuth2. This requires a server to register callbacks against to facilitate the security handshake process.

This process uses certificates - these certificates live on the host machine and are provided by letsencrypt. This is facilitated by a process that runs on the machine periodically to renew the certificate. When this happens, port 80 must be open.

Information about the certificates and the next renewal:

Successfully received certificate.
Certificate is saved at: /etc/letsencrypt/live/dirtydata.ai/fullchain.pem
Key is saved at:         /etc/letsencrypt/live/dirtydata.ai/privkey.pem
This certificate expires on 2026-04-22.
These files will be updated when the certificate renews.
Certbot has set up a scheduled task to automatically renew this certificate in the background.

### Ladder Builder

```python
from src.ladder_builder import LadderBuilder, LadderConfig, AllocationStrategy

config = LadderConfig(
    allocation_strategy=AllocationStrategy.FRONT_WEIGHTED,
    weeks_to_ladder=4,
    base_sigma=1.5
)

builder = LadderBuilder(finnhub_client, strike_optimizer, config)
ladder = builder.build_ladder(
    symbol="NVDA",
    shares=400,
    current_price=185.50,
    volatility=0.35,
    options_chain=chain
)

print(f"Total premium: ${ladder.total_gross_premium:.2f}")
for leg in ladder.actionable_legs:
    print(f"  Week {leg.week_number}: {leg.contracts}x ${leg.strike}")
```

## Project Structure

```
options_income/
├── src/
│   ├── models/                 # Data models
│   │   ├── base.py            # OptionContract, OptionsChain
│   │   ├── profiles.py        # StrikeProfile, DeltaBand enums
│   │   ├── optimization.py    # Strike optimizer results
│   │   ├── strategies.py      # Covered call/put results
│   │   ├── overlay.py         # Scanner models
│   │   └── ladder.py          # Ladder builder models
│   ├── wheel/                  # Wheel strategy implementation
│   │   ├── cli.py             # Command-line interface
│   │   ├── manager.py         # Position management
│   │   ├── recommend.py       # Recommendation engine
│   │   └── repository.py      # Database operations
│   ├── oauth/                  # Schwab OAuth integration
│   │   ├── coordinator.py     # High-level OAuth interface
│   │   ├── token_manager.py   # Token lifecycle management
│   │   └── auth_server.py     # HTTPS callback server
│   ├── cache/                  # Caching infrastructure
│   ├── volatility.py          # Volatility calculations
│   ├── strike_optimizer.py    # Strike selection and probabilities
│   ├── covered_strategies.py  # Covered call/put/wheel analysis
│   ├── risk_analyzer.py       # Risk and income metrics
│   ├── overlay_scanner.py     # Weekly overlay recommendations
│   ├── ladder_builder.py      # Multi-week ladder positions
│   ├── earnings_calendar.py   # Earnings date tracking
│   ├── finnhub_client.py      # Finnhub API client
│   └── price_fetcher.py       # Alpha Vantage price fetcher
├── scripts/
│   ├── authorize_schwab_host.py   # OAuth authorization (HOST)
│   └── check_schwab_auth.py       # OAuth status checker (CONTAINER)
├── tests/                      # 105 OAuth + 446 core tests
├── docs/                       # Documentation
│   ├── prd.md                 # Product requirements
│   ├── system_design.md       # System architecture
│   ├── oauth_design.md        # OAuth design specification
│   ├── oauth_requirements.md  # OAuth requirements
│   └── CONTAINER_ARCHITECTURE.md  # Container deployment guide
├── example_end_to_end.py      # Complete workflow example
└── wheel_strategy_tool.py     # Production wheel strategy CLI
```

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_risk_analyzer.py -v

# Run OAuth tests only
pytest tests/oauth/ -v

# Run wheel strategy tests only
pytest tests/wheel/ -v
```

**Current Test Coverage:**
- Core modules: 446 tests, 79% coverage
- OAuth module: 105 tests, 93% coverage
- **Total: 551 tests**

## Code Quality

```bash
# Lint code
ruff check .

# Format code
ruff format .
```

## Risk Profile Presets

| Profile | Sigma Range | P(ITM) Target | Use Case |
|---------|-------------|---------------|----------|
| Aggressive | 0.5-1.0σ | 30-40% | Higher premium, more risk |
| Moderate | 1.0-1.5σ | 15-30% | Balanced approach |
| Conservative | 1.5-2.0σ | 7-15% | Lower risk, steady income |
| Defensive | 2.0-2.5σ | 2-7% | Maximum protection |

## Delta Band Presets (Weekly Options)

| Band | Delta Range | Characteristics |
|------|-------------|-----------------|
| Defensive | 0.05-0.10 | Very far OTM, low premium |
| Conservative | 0.10-0.15 | Standard weekly target |
| Moderate | 0.15-0.25 | Higher premium, more risk |
| Aggressive | 0.25-0.35 | Near ATM, high assignment risk |

## Known Limitations

1. **Finnhub Data Accuracy**: Options pricing may be stale; verify before trading
2. **API Rate Limits**: Finnhub (60/min free), Alpha Vantage (25/day free)
3. **Black-Scholes Assumptions**: Model assumes log-normal returns, no dividends
4. **Not Financial Advice**: Educational purposes only; verify all data before trading

## API Keys

- **Finnhub**: Free at [finnhub.io/register](https://finnhub.io/register)
- **Alpha Vantage**: Free at [alphavantage.co/support](https://www.alphavantage.co/support/#api-key)

## Documentation

- [Product Requirements](docs/prd.md)
- [System Design](docs/system_design.md)
- [Implementation Plan](IMPLEMENTATION_PLAN.md)

## License

MIT License - See LICENSE file for details.

---

**Disclaimer**: This software is for educational and informational purposes only. Options trading involves significant risk of loss. Always verify data with multiple sources and consult a financial advisor before making trading decisions.
