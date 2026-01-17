# Product Requirements Document (PRD)
## Covered Options Strategy Optimization System

**Version:** 2.0  
**Date:** January 15, 2026  
**Author:** Stock Quant  
**Status:** Draft

---

## 1. Executive Summary

This document outlines the requirements for a Python-based system to retrieve options chain data, calculate volatility metrics, and optimize strike selection for covered call and covered put strategies. The system integrates data from Finnhub and Alpha Vantage APIs to provide comprehensive options analysis capabilities.

### 1.1 Business Context

Options trading requires access to real-time and accurate options chain data including strike prices, expiration dates, premiums (bid/ask prices), volume, open interest, and Greeks. Additionally, effective covered options strategies require:

- **Historical price data**: For volatility calculations
- **Corporate event calendars**: For risk management around earnings and dividends
- **Strike optimization**: To balance premium income against assignment probability

This system will provide a foundation for:

- **Covered call strategies**: Selling call options against long stock positions to generate income
- **Covered put strategies**: Selling put options with cash reserves to potentially acquire stock at favorable prices
- **Wheel strategy**: Combining covered puts and calls in a systematic cycle
- **Options analysis**: Evaluating option pricing, liquidity, and risk metrics
- **Portfolio management**: Monitoring and managing options positions

### 1.2 Key Objectives

1. Establish reliable connections to Finnhub and Alpha Vantage APIs
2. Retrieve comprehensive options chain data for specified equity tickers
3. Calculate multiple volatility measures from historical price data
4. Optimize strike selection based on volatility and risk preferences
5. Support laddered positions across multiple weekly expirations
6. Provide event risk filtering (earnings, dividends)
7. Implement local caching to minimize API calls

### 1.3 Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| API connection reliability | 99%+ success rate | Error logging |
| Volatility calculation accuracy | ±5% vs. benchmark | Compare to Yahoo Finance/Bloomberg |
| Strike recommendation precision | Nearest tradeable strike | Options chain validation |
| Assignment probability accuracy | ±10% vs. actual outcomes | Backtesting over 1 year |
| Premium capture rate | >90% of theoretical | Live trading results |
| System latency | <500ms for full calculation | Performance testing |
| API efficiency | Minimize calls within rate limits | Usage tracking |

---

## 2. Product Overview

### 2.1 Product Description

A Python application that interfaces with Finnhub and Alpha Vantage APIs to:

1. **Data Retrieval Layer**
   - Fetch options chain data (strikes, expirations, Greeks, IV)
   - Fetch historical OHLC price data with dividends and splits
   - Fetch earnings calendar for event risk management
   - Cache data locally to minimize API calls

2. **Volatility Engine**
   - Calculate multiple volatility measures (Close-to-Close, Parkinson, Garman-Klass, Yang-Zhang)
   - Blend realized and implied volatility
   - Detect volatility regime changes

3. **Strike Optimizer**
   - Calculate strikes at N standard deviations from current price
   - Estimate assignment probabilities
   - Filter by liquidity and spread
   - Support risk profiles (Aggressive, Moderate, Conservative, Defensive)

4. **Ladder Builder**
   - Distribute positions across multiple weekly expirations
   - Adjust strikes by time to expiration
   - Avoid earnings weeks automatically

5. **Risk Analyzer**
   - Calculate income metrics (annualized yield, return if flat/called)
   - Estimate expected value and risk-adjusted returns
   - Provide scenario analysis

### 2.2 Target Users

- **Primary**: Individual investors writing covered calls and puts for income
- **Secondary**: 
  - Quantitative analysts building options strategies
  - Portfolio managers optimizing yield enhancement programs
  - Financial advisors managing client options overlays
  - Algorithmic trading systems requiring volatility inputs
  - Software developers building trading systems

### 2.3 User Stories

**US-1: Conservative Income Investor**
> As a retiree with a stock portfolio, I want to write covered calls that have less than 15% chance of assignment, so that I can generate income while keeping my shares for dividends.

**US-2: Aggressive Income Trader**
> As an active trader, I want to maximize premium income by writing calls closer to the money, accepting higher assignment risk for better returns.

**US-3: Stock Acquirer**
> As an investor with cash reserves, I want to write covered puts on stocks I want to own, so I can either collect premium or acquire shares at a discount.

**US-4: Wheel Strategy Practitioner**
> As a systematic trader, I want to alternate between covered puts and calls, so I can maximize premium income throughout the ownership cycle.

**US-5: Systematic Trader**
> As a quant, I want volatility calculations I can trust, so I can build models that consistently select optimal strikes across many positions.

**US-6: Portfolio Manager**
> As a PM running a covered call overlay, I want to ladder positions across multiple weeks to smooth income and reduce timing risk.

---

## 3. Functional Requirements

### 3.1 Data Sources and API Integration

#### 3.1.1 Finnhub API Integration

**FR-1: Finnhub Authentication**
- System must securely store and use Finnhub API key
- API key configurable via environment variable (`FINNHUB_API_KEY`)
- Validate API key before making requests

**FR-2: Options Chain Retrieval**
- Use endpoint: `GET /api/v1/stock/option-chain`
- Retrieve all available expiration dates for specified ticker
- Fetch all strike prices for each expiration
- Include both call and put options
- Capture pricing data (bid, ask, last), volume, open interest
- Collect Greeks (delta, gamma, theta, vega, rho) and implied volatility

**FR-3: Earnings Calendar Retrieval**
- Use endpoint: `GET /api/v1/calendar/earnings`
- Query earnings dates for specified ticker
- Support date range queries (next 30-60 days)
- Cache results locally (refresh weekly)

**FR-4: Current Stock Price**
- Use endpoint: `GET /api/v1/quote`
- Retrieve real-time stock price for strike calculations

**FR-5: Finnhub Rate Limit Management**
- Respect rate limits: 60 calls/minute, 30 calls/second (free tier)
- Implement retry logic with exponential backoff
- Track API call count for monitoring

#### 3.1.2 Alpha Vantage API Integration

**FR-6: Alpha Vantage Authentication**
- System must securely store and use Alpha Vantage API key
- API key configurable via environment variable (`ALPHA_VANTAGE_API_KEY`)
- Validate API key before making requests

**FR-7: Historical Price Data Retrieval**
- Use endpoint: `TIME_SERIES_DAILY` (free tier)
- Retrieve OHLC data with volume
- Support `outputsize=compact` (100 days) for routine updates
- Parse response into standard OHLC structure
- **Note**: `TIME_SERIES_DAILY_ADJUSTED` (with dividends/splits) requires premium subscription
- **Limitation**: Volatility calculations use unadjusted closes; rare splits within 100-day window may affect accuracy

**FR-8: Alpha Vantage API Efficiency**
- **Critical**: Pack API calls as densely as possible due to daily limits
- Free tier: 25 requests/day limit
- Use `TIME_SERIES_DAILY` to get OHLC + volume (free tier)
- Cache aggressively (24-hour TTL for price data)
- Target: 1 Alpha Vantage call per ticker per day after initial load
- **Note**: Dividend/split data requires premium `TIME_SERIES_DAILY_ADJUSTED`

**FR-9: Alpha Vantage Rate Limit Management**
- Enforce daily call limit (25/day free tier)
- Track daily usage with reset at midnight
- Provide clear warnings when approaching limit
- Queue requests if limit reached

#### 3.1.3 Data Caching

**FR-10: Local File Cache**
- Cache historical price data to local filesystem
- Cache format: JSON or CSV with metadata
- Cache location: Configurable, default `~/.options_cache/`
- Cache key: `{symbol}_{data_type}_{date}.json`

**FR-11: Cache Invalidation**
- Price data: Refresh daily for active tickers
- Options chain: Refresh per session (no persistent cache)
- Earnings calendar: Refresh weekly
- Provide manual cache clear command

**FR-12: Cache-First Data Retrieval**
- Check cache before making API calls
- Return cached data if fresh (within TTL)
- Update cache after successful API calls
- Log cache hits/misses for monitoring

### 3.2 Options Chain Data

**FR-13: Options Chain Parsing**
- Verify API response structure
- Check for missing or null values
- Validate data types (prices as floats, dates as strings)
- Flag anomalous data (negative prices, zero OI on recent expirations)

**FR-14: Options Chain Output**
- Output data in structured JSON format
- Include summary statistics (total contracts, expiration count)
- Group options by expiration date
- Sort strikes in ascending order
- Separate calls and puts clearly
- Calculate derived metrics (bid-ask spread, moneyness)

### 3.3 Volatility Calculation

**FR-15: Close-to-Close Volatility**
- Calculate annualized volatility from daily closing prices
- Support configurable lookback windows (default: 20, 60 days)
- Formula: σ = std(ln(P_t/P_{t-1})) × √252
- Handle missing data points gracefully (skip, don't interpolate)

**FR-16: Parkinson Volatility (High-Low)**
- Calculate volatility using daily high-low range
- More efficient estimator than close-to-close (~5.2x)
- Formula: σ = √(1/(4n×ln(2)) × Σln(H_i/L_i)²) × √252
- Requires OHLC data

**FR-17: Garman-Klass Volatility**
- Calculate volatility using OHLC data
- Most efficient estimator for daily data (~7.4x)
- Formula: σ = √(1/n × Σ[0.5×ln(H/L)² - (2ln(2)-1)×ln(C/O)²]) × √252
- Handle overnight gaps appropriately

**FR-18: Yang-Zhang Volatility**
- Calculate volatility accounting for overnight jumps
- Best estimator when overnight moves are significant (~8.0x efficiency)
- Combines overnight, open-to-close, and Rogers-Satchell components
- Recommended for stocks with significant pre/post-market activity

**FR-19: Implied Volatility Extraction**
- Extract ATM implied volatility from options chain data
- Interpolate IV for exact ATM strike if not available
- Support IV extraction for specific expirations
- Calculate IV term structure across expirations

**FR-20: Volatility Blending**
- Combine realized and implied volatility with configurable weights
- Default blend: 30% RV(20d) + 20% RV(60d) + 50% IV(ATM)
- Allow user override of blending weights
- Provide rationale for recommended blend

**FR-21: Volatility Regime Detection**
- Classify current volatility regime (Low/Normal/High/Extreme)
- Compare current vol to historical percentiles
- Adjust recommendations based on regime
- Alert when regime change detected

### 3.4 Strike Selection

**FR-22: Standard Deviation Strike Calculation**
- Calculate strike price at N standard deviations from current price
- Formula: K = S × exp(n × σ × √T)
- Support both call (positive n) and put (negative n) strikes
- Account for time to expiration in days

**FR-23: Strike Rounding**
- Round calculated strike to nearest tradeable strike
- Support different strike increments ($0.50, $1.00, $2.50, $5.00)
- Prefer rounding direction based on strategy (conservative = round up for calls, round down for puts)
- Return both theoretical and tradeable strikes

**FR-24: Assignment Probability Estimation**
- Calculate P(ITM at expiration) for each strike
- Use Black-Scholes N(-d2) approximation for calls, N(d2) for puts
- Provide delta as proxy for instantaneous assignment probability
- Support Monte Carlo simulation for more accurate estimates (optional)

**FR-25: Strike Profile Selection**
- Provide preset strike profiles with standard deviations:
  - Aggressive: 0.5-1.0σ OTM (30-40% P(ITM))
  - Moderate: 1.0-1.5σ OTM (15-30% P(ITM))
  - Conservative: 1.5-2.0σ OTM (7-15% P(ITM))
  - Defensive: 2.0-2.5σ OTM (2-7% P(ITM))
- Allow custom σ input

**FR-26: Multi-Strike Recommendations**
- Return array of candidate strikes with metrics
- Include: strike, σ distance, delta, P(ITM), premium estimate
- Sort by user preference (income, safety, or balanced)
- Filter by liquidity (open interest > threshold, bid-ask spread < threshold)

### 3.5 Covered Call Strategy

**FR-27: Covered Call Analysis**
- Identify OTM call strikes above current stock price
- Calculate premium income (bid prices)
- Estimate assignment probability
- Calculate returns: if flat, if called, breakeven

**FR-28: Covered Call Recommendations**
- Recommend strikes based on user's risk profile
- Consider liquidity (open interest > 100)
- Flag wide bid-ask spreads (>10% of premium)
- Warn if expiration spans earnings date

### 3.6 Covered Put Strategy

**FR-29: Covered Put Analysis**
- Identify OTM put strikes below current stock price
- Calculate premium income (bid prices)
- Calculate collateral requirement (strike × 100)
- Estimate assignment probability
- Calculate returns: if OTM (keep premium), if assigned (effective purchase price)

**FR-30: Covered Put Recommendations**
- Recommend strikes based on user's risk profile and target purchase price
- Consider liquidity (open interest > 100)
- Flag wide bid-ask spreads (>10% of premium)
- Warn if expiration spans earnings or ex-dividend date

**FR-31: Early Assignment Risk for Puts**
- Flag deep ITM puts near ex-dividend dates
- Calculate early assignment probability
- Warn user of elevated assignment risk

### 3.7 Wheel Strategy Support

**FR-32: Wheel Strategy State Tracking**
- Track current state: Cash (sell puts) vs. Shares (sell calls)
- Recommend appropriate strategy based on current holdings
- Calculate cycle metrics (total premium collected, average cost basis)

**FR-33: Wheel Strategy Recommendations**
- If holding cash: Recommend put strikes to potentially acquire shares
- If holding shares: Recommend call strikes to generate income or exit position
- Provide expected outcomes for each recommendation

### 3.8 Ladder Strategy

**FR-34: Weekly Expiration Detection**
- Identify next N weekly expirations from options chain
- Handle standard weekly options (Friday expiry)
- Handle Wednesday/Monday weeklies if present
- Skip expirations with earnings dates when configured

**FR-35: Position Allocation**
- Distribute total shares/cash across N weeks
- Support equal allocation (100/N per week)
- Support front-weighted allocation (more in near-term)
- Support back-weighted allocation (more in far-term)
- Ensure allocations sum to total position size

**FR-36: Strike Adjustment by Week**
- Adjust σ distance based on time to expiration
- Near-term (Week 1): Slightly more aggressive (n - 0.25σ)
- Mid-term (Week 2-3): Baseline σ
- Far-term (Week 4): Slightly more conservative (n + 0.25σ)
- Rationale: Near-term has accelerating theta, less time for adverse moves

**FR-37: Ladder Output**
- Return complete ladder specification:
  - Expiration date
  - Recommended strike
  - Option type (Call/Put)
  - Number of contracts
  - Expected premium (bid price × contracts × 100)
  - Assignment probability
  - Max profit scenarios

### 3.9 Risk Analysis

**FR-38: Event Risk Filter**
- Accept earnings date calendar (from Finnhub)
- Accept dividend calendar (from Alpha Vantage)
- Flag expirations that span earnings
- Flag puts near ex-dividend dates (early assignment risk)
- Warn user of elevated risk around events
- Optionally exclude event weeks from ladder

**FR-39: Income Metrics**
- Calculate annualized yield: (Premium / Stock Price) × (365 / DTE)
- Calculate return if flat: Premium / Stock Price
- Calculate return if called/assigned: (Premium + (Strike - Stock Price)) / Stock Price
- Calculate breakeven: Stock Price - Premium (for calls), Strike - Premium (for puts)

**FR-40: Risk Metrics**
- Calculate expected value: P(OTM) × Premium - P(ITM) × Opportunity Cost
- Estimate opportunity cost (requires price target input)
- Calculate risk-adjusted return (Sharpe-like ratio)
- Provide downside protection percentage

**FR-41: Scenario Analysis**
- Calculate outcomes at various price points
- Show P&L at: -10%, -5%, ATM, Strike, +5%, +10%
- Compare to buy-and-hold scenarios
- Support custom scenario inputs

---

## 4. Non-Functional Requirements

### 4.1 Performance

**NFR-1: API Response Time**
- API response time should be under 5 seconds for typical requests
- Timeout configuration for API calls (default: 10 seconds)

**NFR-2: Calculation Speed**
- Volatility calculation: <100ms for 252 days of data
- Strike optimization: <50ms per ticker
- Full ladder generation: <200ms
- Data parsing and processing: <2 seconds

**NFR-3: Memory Efficiency**
- Memory usage: <50MB for single ticker analysis
- Handle options chains with 1000+ contracts efficiently
- No memory leaks in long-running processes

**NFR-4: Numerical Precision**
- Volatility: 4 decimal places (e.g., 0.2534 = 25.34%)
- Strike prices: 2 decimal places
- Probabilities: 4 decimal places
- Use appropriate precision for currency calculations

### 4.2 Reliability

**NFR-5: API Error Handling**
- Handle rate limits without crashing (HTTP 429)
- Graceful error handling for network failures
- Retry logic with exponential backoff for transient errors
- Clear error messages for common failure scenarios

**NFR-6: Input Validation**
- Validate all input data types and ranges
- Reject invalid data with clear error messages
- Handle edge cases (zero prices, negative values)

**NFR-7: Numerical Stability**
- Handle extreme volatility values (0% to 500%)
- Handle very small/large stock prices
- Avoid division by zero and overflow conditions
- Use numerically stable algorithms

**NFR-8: Graceful Degradation**
- Return partial results if some calculations fail
- Fall back to simpler methods if advanced methods fail
- Log warnings for degraded operation
- Continue operation if one API is unavailable

### 4.3 Security

**NFR-9: API Key Management**
- API keys must not be hardcoded in source code
- API keys stored in environment variables
- Support for .env files (added to .gitignore)
- No sensitive data logged to console or files

**NFR-10: Input Sanitization**
- Sanitize ticker symbols (uppercase, alphanumeric only)
- Validate all user inputs before API calls
- Prevent injection attacks

### 4.4 Maintainability

**NFR-11: Code Quality**
- Code must follow PEP 8 style guidelines
- Comprehensive inline documentation (docstrings)
- Type hints for all functions
- Pylint score >9.0
- Black formatted

**NFR-12: Testing**
- Unit tests with >80% code coverage (>90% for core modules)
- Integration tests with sample data
- Property-based tests for mathematical functions
- Benchmark tests for performance validation

**NFR-13: Documentation**
- README with setup instructions
- API reference documentation
- Mathematical methodology document
- Usage examples for all features
- Known limitations and disclaimers

### 4.5 Extensibility

**NFR-14: Modular Design**
- API clients as pluggable components
- Volatility calculators as pluggable components
- Strike selectors as strategy pattern
- Easy to add new data sources
- Easy to add new volatility estimators

**NFR-15: Configuration**
- All parameters configurable via dataclass
- Support configuration files (YAML/JSON)
- Environment variable overrides
- Sensible defaults for all parameters

### 4.6 Usability

**NFR-16: Command-Line Interface**
- Clear command-line interface with help text
- Multiple output formats (JSON, summary, minimal)
- File output support
- Verbose/debug logging option

**NFR-17: Error Messages**
- Helpful error messages with actionable guidance
- Suggest fixes for common configuration errors
- Provide API documentation links when relevant

---

## 5. Technical Specifications

### 5.1 Technology Stack

- **Language**: Python 3.9+
- **HTTP Library**: requests
- **Data APIs**: 
  - Finnhub Stock API (https://finnhub.io)
  - Alpha Vantage API (https://www.alphavantage.co)
- **Testing**: pytest
- **Linting**: pylint, black
- **Type Checking**: mypy

### 5.2 API Endpoints

#### 5.2.1 Finnhub Endpoints

| Endpoint | Purpose | Rate Limit |
|----------|---------|------------|
| `GET /api/v1/stock/option-chain` | Options chain data | 60/min |
| `GET /api/v1/quote` | Current stock price | 60/min |
| `GET /api/v1/calendar/earnings` | Earnings dates | 60/min |

**Options Chain Response Structure**:
```json
{
  "data": [
    {
      "expirationDate": "2026-01-16",
      "strike": 10.0,
      "type": "Call",
      "bid": 1.25,
      "ask": 1.30,
      "last": 1.27,
      "volume": 1500,
      "openInterest": 5000,
      "delta": 0.55,
      "gamma": 0.08,
      "theta": -0.05,
      "vega": 0.12,
      "rho": 0.03,
      "impliedVolatility": 0.35
    }
  ]
}
```

#### 5.2.2 Alpha Vantage Endpoints

| Endpoint | Purpose | Rate Limit | Tier |
|----------|---------|------------|------|
| `TIME_SERIES_DAILY` | OHLC + volume | 25/day | Free |
| `TIME_SERIES_DAILY_ADJUSTED` | OHLC + dividends + splits | 25/day | Premium |

**TIME_SERIES_DAILY Response Structure** (free tier):
```json
{
  "Meta Data": {
    "1. Information": "Daily Prices (open, high, low, close) and Volumes",
    "2. Symbol": "F",
    "3. Last Refreshed": "2026-01-15"
  },
  "Time Series (Daily)": {
    "2026-01-15": {
      "1. open": "10.50",
      "2. high": "10.75",
      "3. low": "10.40",
      "4. close": "10.65",
      "5. volume": "45000000"
    }
  }
}
```

**Note**: `TIME_SERIES_DAILY_ADJUSTED` (with adjusted close, dividends, splits) requires premium subscription.

### 5.3 Data Requirements

#### 5.3.1 Historical Price Data

| Field | Type | Required | Source | Description |
|-------|------|----------|--------|-------------|
| date | datetime | Yes | Alpha Vantage | Trading date |
| open | float | Yes | Alpha Vantage | Opening price |
| high | float | Yes | Alpha Vantage | Daily high |
| low | float | Yes | Alpha Vantage | Daily low |
| close | float | Yes | Alpha Vantage | Closing price |
| volume | int | Yes | Alpha Vantage | Trading volume |
| adjusted_close | float | No* | Alpha Vantage | Split/dividend adjusted close |
| dividend | float | No* | Alpha Vantage | Dividend amount (0 if none) |
| split_coefficient | float | No* | Alpha Vantage | Split ratio (1.0 if none) |

*Premium only: adjusted_close, dividend, and split_coefficient require `TIME_SERIES_DAILY_ADJUSTED` (premium subscription)

**Data Window Requirements**:

| Window | Days | Purpose |
|--------|------|---------|
| Minimum | 20 | Short-term realized volatility |
| Recommended | 60 | Standard volatility calculation |
| Extended | 252 | Full year for regime comparison |
| Maximum | 504 | Two years for percentile ranking |

#### 5.3.2 Options Chain Data

| Field | Type | Required | Source | Description |
|-------|------|----------|--------|-------------|
| expiration_date | str | Yes | Finnhub | Option expiration (YYYY-MM-DD) |
| strike | float | Yes | Finnhub | Strike price |
| option_type | str | Yes | Finnhub | "Call" or "Put" |
| bid | float | Yes | Finnhub | Current bid price |
| ask | float | Yes | Finnhub | Current ask price |
| last | float | No | Finnhub | Last traded price |
| volume | int | No | Finnhub | Daily volume |
| open_interest | int | Yes | Finnhub | Open interest (liquidity) |
| implied_volatility | float | Yes* | Finnhub | IV from market maker |
| delta | float | No | Finnhub | Option delta |
| gamma | float | No | Finnhub | Option gamma |
| theta | float | No | Finnhub | Option theta |
| vega | float | No | Finnhub | Option vega |
| rho | float | No | Finnhub | Option rho |

*Required for IV-based calculations

#### 5.3.3 Corporate Events Data

| Field | Type | Required | Source | Description |
|-------|------|----------|--------|-------------|
| earnings_date | datetime | No | Finnhub | Next earnings announcement |
| ex_dividend_date | datetime | No | Alpha Vantage | Next ex-dividend date (derived) |
| dividend_amount | float | No | Alpha Vantage | Expected dividend |

### 5.4 Data Quality Considerations

**Known Issues with Finnhub Options Data** (based on GitHub issue #545):
- Bid/ask prices may be stale or inaccurate for some strikes
- ATM options may show significant discrepancies from live market data
- Greeks and contract metadata generally more reliable than pricing
- Data should be verified against other sources for trading decisions

**Mitigation Strategies**:
- Document data source limitations clearly
- Add timestamps to all retrieved data
- Flag potentially stale data (last trade > 24 hours old)
- Cross-reference IV with realized vol for sanity checks
- Use bid price (not mid) for conservative premium estimates

### 5.5 Mathematical Formulas

#### 5.5.1 Volatility Estimators

**Close-to-Close:**
$$\sigma_{CC} = \sqrt{\frac{252}{n-1} \sum_{i=1}^{n} (r_i - \bar{r})^2}$$
where $r_i = \ln(C_i / C_{i-1})$

**Parkinson:**
$$\sigma_P = \sqrt{\frac{252}{4n \ln(2)} \sum_{i=1}^{n} \ln\left(\frac{H_i}{L_i}\right)^2}$$

**Garman-Klass:**
$$\sigma_{GK} = \sqrt{\frac{252}{n} \sum_{i=1}^{n} \left[ \frac{1}{2}\ln\left(\frac{H_i}{L_i}\right)^2 - (2\ln(2)-1)\ln\left(\frac{C_i}{O_i}\right)^2 \right]}$$

**Yang-Zhang:**
$$\sigma_{YZ} = \sqrt{\sigma_o^2 + k\sigma_c^2 + (1-k)\sigma_{RS}^2}$$
where $k = 0.34 / (1.34 + (n+1)/(n-1))$

#### 5.5.2 Strike Calculation

**Strike at N sigma:**
$$K = S \times e^{n \times \sigma \times \sqrt{T}}$$
where:
- $S$ = current stock price
- $n$ = number of standard deviations (positive for calls, negative for puts)
- $\sigma$ = annualized volatility
- $T$ = time to expiration in years

#### 5.5.3 Assignment Probability (Black-Scholes)

**For Calls:** $P(S_T > K) = N(-d_2)$

**For Puts:** $P(S_T < K) = N(d_2)$

where:
$$d_1 = \frac{\ln(S/K) + (r + \sigma^2/2)T}{\sigma\sqrt{T}}$$
$$d_2 = d_1 - \sigma\sqrt{T}$$

---

## 6. Implementation Phases

### Phase 1: Core Data Infrastructure ✓ (Completed)
- ✓ Finnhub API connection and authentication
- ✓ Basic options chain retrieval for single ticker
- ✓ Data parsing and JSON output
- ✓ Error handling with retry logic
- ✓ Basic documentation and tests

### Phase 2: Volatility Engine ✓ (Completed)
- ✓ Close-to-close volatility calculator
- ✓ Parkinson volatility calculator
- ✓ Garman-Klass volatility calculator
- ✓ Yang-Zhang volatility calculator
- ✓ Volatility blending logic
- ✓ Unit tests (33 tests, 91% coverage)
- ✓ Integration helpers (IV extraction, term structure)

### Phase 3: Alpha Vantage Integration & Caching (Current)
- ☐ Alpha Vantage client module
- ☐ TIME_SERIES_DAILY_ADJUSTED data retrieval
- ☐ Dividend and split data extraction
- ☐ Local file-based cache implementation
- ☐ Cache-first data retrieval pattern
- ☐ Daily cache refresh mechanism
- ☐ API usage tracking and limits

### Phase 4: Strike Optimization
- ☐ Strike-at-sigma calculator
- ☐ Strike rounding to tradeable strikes
- ☐ Assignment probability calculator (calls and puts)
- ☐ Strike profile presets
- ☐ Liquidity filtering
- ☐ Strike recommendation engine

### Phase 5: Covered Options Strategies
- ☐ Covered call analysis and recommendations
- ☐ Covered put analysis and recommendations
- ☐ Wheel strategy state tracking
- ☐ Collateral calculations for puts

### Phase 6: Ladder Builder
- ☐ Weekly expiration detection
- ☐ Position allocation strategies
- ☐ Strike adjustment by week
- ☐ Complete ladder generation
- ☐ Earnings avoidance logic (using Finnhub calendar)

### Phase 7: Risk Analysis & Polish
- ☐ Income metrics calculation
- ☐ Risk metrics calculation
- ☐ Scenario analysis engine
- ☐ Event risk filtering (earnings, dividends)
- ☐ Comprehensive documentation
- ☐ Example notebooks

---

## 7. Options Trading Strategies Context

### 7.1 Covered Calls

**Strategy Overview**:
- Own 100 shares of underlying stock
- Sell 1 call option contract against those shares
- Collect premium income
- Willing to sell shares if stock rises above strike

**Data Requirements**:
- Strike prices above current stock price (OTM calls)
- Premium amounts (bid prices)
- Days to expiration
- Open interest (liquidity indicator)
- Implied volatility for strike selection

**Optimal Use Cases**:
- Neutral to slightly bullish outlook
- Willing to sell shares at strike price
- Want to generate income on existing positions

### 7.2 Covered Puts (Cash-Secured Puts)

**Strategy Overview**:
- Set aside cash equal to (strike × 100) as collateral
- Sell 1 put option contract
- Collect premium income
- Willing to buy shares if stock falls below strike

**Data Requirements**:
- Strike prices below current stock price (OTM puts)
- Premium amounts (bid prices)
- Collateral requirements (strike × 100)
- Days to expiration
- Open interest (liquidity indicator)
- Dividend dates (early assignment risk)

**Optimal Use Cases**:
- Bullish outlook on stock
- Willing to buy shares at strike price (effective discount)
- Have cash reserves to deploy

**Early Assignment Considerations**:
- Deep ITM puts near ex-dividend dates may be exercised early
- Counterparty may exercise to capture dividend
- System should flag elevated early assignment risk

### 7.3 Wheel Strategy

**Strategy Overview**:
1. Start with cash → Sell puts
2. If assigned → Now own shares → Sell calls
3. If called away → Back to cash → Sell puts again
4. Repeat cycle

**Data Requirements**:
- All covered call data requirements
- All covered put data requirements
- Position state tracking (cash vs. shares)
- Cost basis tracking for tax purposes

**Benefits**:
- Maximizes premium collection across the cycle
- Systematic approach removes emotion
- Works well in range-bound markets

### 7.4 Laddering Strategy

**Strategy Overview**:
- Distribute positions across multiple expiration dates
- Smooth income stream over time
- Reduce timing risk
- Maintain rolling positions

**Example** (400 shares, 4-week ladder):
| Week | Expiration | Shares | Strike | Premium |
|------|------------|--------|--------|---------|
| 1 | Jan 17 | 100 | $11.00 | $0.35 |
| 2 | Jan 24 | 100 | $11.50 | $0.30 |
| 3 | Jan 31 | 100 | $11.50 | $0.28 |
| 4 | Feb 7 | 100 | $12.00 | $0.25 |

**Benefits**:
- Diversifies expiration risk
- Provides regular income (weekly)
- Reduces impact of single adverse event

---

## 8. Risk and Compliance

### 8.1 Data Accuracy Risk

**Risk**: API data may be inaccurate or stale
**Impact**: Strike recommendations may be suboptimal, premium estimates may be wrong
**Mitigation**: 
- Clear disclaimers in documentation
- Data validation checks
- Timestamp all data
- Use bid price for conservative estimates
- Cross-reference multiple data points

### 8.2 API Dependency Risk

**Risk**: APIs may change, become unavailable, or deprecate endpoints
**Impact**: System may fail to retrieve required data
**Mitigation**: 
- Abstract API calls behind interfaces
- Implement comprehensive error handling
- Version documentation
- Support fallback to cached data
- Design for multi-provider support

### 8.3 Rate Limit Risk

**Risk**: Exceeding API rate limits
**Impact**: Temporary service unavailability, potential account suspension
**Mitigation**: 
- Implement rate limiting on client side
- Track API usage
- Cache aggressively to minimize calls
- Provide clear warnings when approaching limits

### 8.4 Model Risk

**Risk**: Volatility estimates may not accurately predict future moves
**Impact**: Strikes selected may result in unexpected assignment rates
**Mitigation**: 
- Use blended volatility (realized + implied)
- Provide confidence intervals
- Recommend conservative profiles for uncertain regimes
- Backtest recommendations against historical data

### 8.5 Execution Risk

**Risk**: Recommended strikes may not be filled at expected prices
**Impact**: Actual premium income differs from estimates
**Mitigation**:
- Use bid price (not mid) for premium estimates
- Apply slippage factor for wide spreads
- Recommend only liquid strikes (OI > threshold)
- Note spread as percentage of premium

### 8.6 Event Risk

**Risk**: Earnings, dividends, or other events cause outsized moves
**Impact**: Assignment probability much higher than estimated
**Mitigation**:
- Flag earnings dates in recommendations
- Exclude earnings weeks from ladder by default
- Increase σ distance around known events
- Warn user of elevated IV (potential event)
- Flag dividend dates for put early assignment risk

### 8.7 Usage Compliance

**Risk**: Violating API terms of service
**Impact**: Account suspension, legal issues
**Mitigation**: 
- Respect rate limits
- Don't redistribute raw data
- Follow API terms of service
- Monitor usage patterns

---

## 9. Future Considerations

### 9.1 ML/AI Enhancements (Not in Current Scope)

The following ML enhancements are documented for future consideration but are **not** part of the current implementation scope:

1. **Volatility Regime Prediction**: LSTM/Transformer model to predict volatility regime changes
2. **Earnings Surprise Prediction**: XGBoost classifier for earnings impact
3. **Anomaly Detection**: Autoencoder for identifying mispriced options
4. **Sentiment Analysis**: NLP-based sentiment scoring from news
5. **Reinforcement Learning**: DQN for adaptive strike selection

### 9.2 Additional Data Sources

- Real-time streaming data (WebSocket)
- Alternative data providers for redundancy
- Options order flow data
- Institutional positioning data

### 9.3 User Interface

- Web-based dashboard (React + TypeScript)
- Real-time alerts for trading opportunities
- Portfolio tracking and P&L monitoring
- Mobile app support

### 9.4 Advanced Analytics

- Greeks calculation and validation
- Probability analysis beyond Black-Scholes
- Backtesting framework for strategies
- Portfolio-level risk analysis

---

## 10. Acceptance Criteria

### 10.1 Data Infrastructure

| # | Criterion | Verification |
|---|-----------|--------------|
| AC-1 | Successfully authenticate with Finnhub API | Integration test |
| AC-2 | Successfully authenticate with Alpha Vantage API | Integration test |
| AC-3 | Retrieve options chain data for ticker | API response validation |
| AC-4 | Retrieve historical OHLC data with dividends | API response validation |
| AC-5 | Retrieve earnings calendar | API response validation |
| AC-6 | Cache data locally and retrieve from cache | Cache hit/miss test |
| AC-7 | Handle API rate limits gracefully | Rate limit simulation test |
| AC-8 | Handle API errors with clear messages | Error handling test |

### 10.2 Volatility Module

| # | Criterion | Verification |
|---|-----------|--------------|
| AC-9 | Calculate close-to-close vol within 1% of benchmark | Compare to Yahoo Finance |
| AC-10 | Calculate Parkinson vol from OHLC data | Unit test with known inputs |
| AC-11 | Calculate Garman-Klass vol from OHLC data | Unit test with known inputs |
| AC-12 | Calculate Yang-Zhang vol from OHLC data | Unit test with known inputs |
| AC-13 | Blend volatilities with configurable weights | Unit test weight combinations |
| AC-14 | Handle missing data gracefully | Test with gaps in price series |
| AC-15 | Return consistent results for same inputs | Determinism test |

### 10.3 Strike Optimizer

| # | Criterion | Verification |
|---|-----------|--------------|
| AC-16 | Calculate strike at N sigma accurately | Mathematical verification |
| AC-17 | Round to nearest tradeable strike | Test against options chain |
| AC-18 | Calculate assignment probability (calls) | Compare to option delta |
| AC-19 | Calculate assignment probability (puts) | Compare to option delta |
| AC-20 | Filter by liquidity thresholds | Test with varying OI/spread |
| AC-21 | Return ranked recommendations | Verify sorting logic |

### 10.4 Covered Options Strategies

| # | Criterion | Verification |
|---|-----------|--------------|
| AC-22 | Generate covered call recommendations | Integration test |
| AC-23 | Generate covered put recommendations | Integration test |
| AC-24 | Calculate collateral requirements for puts | Unit test |
| AC-25 | Flag early assignment risk for puts | Test with dividend dates |

### 10.5 Ladder Builder

| # | Criterion | Verification |
|---|-----------|--------------|
| AC-26 | Identify correct weekly expirations | Test against known chain |
| AC-27 | Allocate shares correctly across weeks | Sum to total shares |
| AC-28 | Adjust sigma by week appropriately | Verify near < mid < far |
| AC-29 | Exclude earnings weeks when configured | Test with earnings date |
| AC-30 | Generate complete ladder specification | All fields populated |

### 10.6 Integration & Quality

| # | Criterion | Verification |
|---|-----------|--------------|
| AC-31 | All code documented and type-hinted | Docstring coverage |
| AC-32 | Unit test coverage >80% | Coverage report |
| AC-33 | Code passes linting (pylint >9.0) | Linting report |
| AC-34 | Complete calculation in <500ms | Performance test |
| AC-35 | README provides clear setup instructions | Manual review |

---

## 11. Documentation Requirements

- README with setup instructions for both APIs
- API authentication guide (Finnhub and Alpha Vantage)
- Code documentation (docstrings)
- Type hints for all functions
- Unit test coverage report
- Example usage scenarios
- Data structure documentation
- Mathematical methodology document
- Known limitations and disclaimers
- Cache management guide

---

## 12. Appendix

### A. Glossary

| Term | Definition |
|------|------------|
| **Strike Price** | The price at which an option can be exercised |
| **Expiration Date** | The date when an option contract expires |
| **Premium** | The price paid/received for an option contract |
| **Bid/Ask Spread** | Difference between highest buy price and lowest sell price |
| **Open Interest** | Total number of outstanding option contracts |
| **Greeks** | Risk sensitivity measures (delta, gamma, theta, vega, rho) |
| **Implied Volatility (IV)** | Market's forecast of likely movement in security price |
| **Realized Volatility (RV)** | Historical volatility calculated from past price movements |
| **ATM** | At-the-money (strike price near current stock price) |
| **OTM** | Out-of-the-money (call strike > stock price, put strike < stock price) |
| **ITM** | In-the-money (call strike < stock price, put strike > stock price) |
| **Sigma (σ)** | Standard deviation; used as unit of price movement |
| **Delta** | Option sensitivity to stock price; approximates P(ITM) |
| **Assignment** | Exercise of option by buyer, requiring seller to fulfill contract |
| **Ladder** | Distribution of positions across multiple expirations |
| **DTE** | Days to expiration |
| **Annualized** | Scaled to annual basis using √252 trading days |
| **Covered Call** | Selling a call option while owning the underlying shares |
| **Covered Put** | Selling a put option while holding cash as collateral |
| **Wheel Strategy** | Systematic rotation between covered puts and covered calls |
| **OHLC** | Open, High, Low, Close - standard price data format |
| **Ex-Dividend Date** | Date by which you must own shares to receive the dividend |

### B. Volatility Estimator Comparison

| Estimator | Efficiency | Data Required | Overnight Gaps | Best Use Case |
|-----------|------------|---------------|----------------|---------------|
| Close-to-Close | 1.0x | Close only | Not handled | Simple baseline |
| Parkinson | 5.2x | High, Low | Not handled | Most stocks |
| Garman-Klass | 7.4x | OHLC | Not handled | Liquid stocks |
| Yang-Zhang | 8.0x | OHLC | Handled | Stocks with gaps |

*Efficiency relative to close-to-close estimator

### C. Strike Profile Details

| Profile | σ Distance | Target P(ITM) | Typical Delta | Annual Yield* |
|---------|------------|---------------|---------------|---------------|
| Aggressive | 0.5-1.0 | 30-40% | 0.30-0.40 | 20-40% |
| Moderate | 1.0-1.5 | 15-30% | 0.15-0.30 | 10-20% |
| Conservative | 1.5-2.0 | 7-15% | 0.07-0.15 | 5-10% |
| Defensive | 2.0-2.5 | 2-7% | 0.02-0.07 | 2-5% |

*Approximate, varies significantly with underlying volatility

### D. API Rate Limits Summary

| API | Endpoint | Free Tier Limit | Caching Strategy |
|-----|----------|-----------------|------------------|
| Finnhub | Options Chain | 60/min | Per-session |
| Finnhub | Quote | 60/min | Per-session |
| Finnhub | Earnings Calendar | 60/min | Weekly cache |
| Alpha Vantage | TIME_SERIES_DAILY | 25/day | Daily cache (24h TTL) |
| Alpha Vantage | TIME_SERIES_DAILY_ADJUSTED | 25/day | Premium only |

### E. References

- Finnhub API Documentation: https://finnhub.io/docs/api
- Alpha Vantage API Documentation: https://www.alphavantage.co/documentation/
- Finnhub Issue #545 (Options pricing concerns): https://github.com/finnhubio/Finnhub-API/issues/545
- Hull, J. "Options, Futures, and Other Derivatives" - Volatility estimation
- Taleb, N. "Dynamic Hedging" - Practical volatility measurement
- Natenberg, S. "Option Volatility and Pricing" - IV analysis
- Yang, D. & Zhang, Q. (2000) "Drift Independent Volatility Estimation"
- Garman, M. & Klass, M. (1980) "On the Estimation of Security Price Volatilities"
- Parkinson, M. (1980) "The Extreme Value Method for Estimating the Variance"
- Options Trading Fundamentals: OCC Options Disclosure Document

---

## 13. Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-13 | Stock Quant | Initial PRD for Finnhub options chain retrieval |
| 1.1 | 2026-01-14 | Stock Quant | Added strike optimization requirements (separate doc) |
| 2.0 | 2026-01-15 | Stock Quant | Consolidated PRD: merged strike optimization, added covered puts, added Alpha Vantage integration, added caching requirements |

---

**Approval Sign-off**

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Product Owner | | | |
| Technical Lead | | | |
| QA Lead | | | |
