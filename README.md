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

- **Finnhub**: Options chains, earnings calendar
- **Alpha Vantage**: Historical price data with dividends and splits

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set API Keys

```bash
export FINNHUB_API_KEY="your_finnhub_key"
export ALPHA_VANTAGE_API_KEY="your_alpha_vantage_key"
```

Or create a `.env` file:
```
FINNHUB_API_KEY=your_finnhub_key
ALPHA_VANTAGE_API_KEY=your_alpha_vantage_key
```

### 3. Run Example

```bash
python example_end_to_end.py
```

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
├── tests/                      # 446 unit tests
├── docs/                       # Documentation
└── example_end_to_end.py      # Complete workflow example
```

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_risk_analyzer.py -v
```

Current: 446 tests, 79% coverage

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
