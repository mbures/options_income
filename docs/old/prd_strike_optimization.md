# Product Requirements Document (PRD)
## Covered Call Strike Optimization System

**Version:** 1.0  
**Date:** January 14, 2026  
**Author:** Stock Quant  
**Status:** Draft  
**Parent System:** Finnhub Options Chain Data Retrieval System

---

## 1. Executive Summary

This document outlines the requirements for developing a volatility-based strike optimization module for covered call strategies. The system calculates optimal strike prices expressed in standard deviations from the current stock price, balancing premium income against assignment probability.

### 1.1 Business Context

Covered call writing is a popular income-generating strategy where an investor sells call options against shares they own. The critical decision is **strike selection**:

- **Too close to current price**: Higher premium, but high probability of shares being called away
- **Too far from current price**: Lower premium, shares rarely called away but minimal income

This system provides a quantitative framework to optimize this tradeoff by:
1. Calculating realized and implied volatility
2. Expressing strike distances in standard deviations (σ)
3. Estimating assignment probabilities
4. Recommending strikes based on user risk preferences
5. Supporting laddered positions across multiple weekly expirations

### 1.2 Key Objectives

1. Calculate accurate volatility estimates from historical price data
2. Blend realized and implied volatility for forward-looking estimates
3. Convert volatility to actionable strike recommendations
4. Support weekly options with 1-4 week laddering strategies
5. Provide assignment probability estimates for each strike
6. Integrate seamlessly with existing Finnhub options infrastructure

### 1.3 Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Volatility calculation accuracy | ±5% vs. Bloomberg/Reuters | Benchmark comparison |
| Strike recommendation precision | Nearest tradeable strike | Options chain validation |
| Assignment probability accuracy | ±10% vs. actual outcomes | Backtesting over 1 year |
| Premium capture rate | >90% of theoretical | Live trading results |
| System latency | <500ms for full calculation | Performance testing |

---

## 2. Product Overview

### 2.1 Product Description

A Python module that integrates with the existing Finnhub options system to provide:

1. **Volatility Engine**: Calculates multiple volatility measures from price data
2. **Strike Calculator**: Converts volatility to strike price recommendations
3. **Probability Estimator**: Calculates likelihood of assignment at each strike
4. **Ladder Builder**: Distributes positions across multiple weekly expirations
5. **Risk Analyzer**: Evaluates income vs. assignment tradeoff metrics

### 2.2 Target Users

- **Primary**: Individual investors writing covered calls for income
- **Secondary**: 
  - Quantitative analysts building options strategies
  - Portfolio managers optimizing yield enhancement programs
  - Financial advisors managing client options overlays
  - Algorithmic trading systems requiring volatility inputs

### 2.3 User Stories

**US-1: Conservative Income Investor**
> As a retiree with a stock portfolio, I want to write covered calls that have less than 15% chance of assignment, so that I can generate income while keeping my shares for dividends.

**US-2: Aggressive Income Trader**
> As an active trader, I want to maximize premium income by writing calls closer to the money, accepting higher assignment risk for better returns.

**US-3: Systematic Trader**
> As a quant, I want volatility calculations I can trust, so I can build models that consistently select optimal strikes across many positions.

**US-4: Portfolio Manager**
> As a PM running a covered call overlay, I want to ladder positions across multiple weeks to smooth income and reduce timing risk.

---

## 3. Functional Requirements

### 3.1 Volatility Calculation

**FR-1: Realized Volatility - Close-to-Close**
- Calculate annualized volatility from daily closing prices
- Support configurable lookback windows (default: 20, 60 days)
- Formula: σ = std(ln(P_t/P_{t-1})) × √252
- Handle missing data points gracefully (skip, don't interpolate)

**FR-2: Realized Volatility - Parkinson (High-Low)**
- Calculate volatility using daily high-low range
- More efficient estimator than close-to-close
- Formula: σ = √(1/(4n×ln(2)) × Σln(H_i/L_i)²) × √252
- Requires OHLC data

**FR-3: Realized Volatility - Garman-Klass**
- Calculate volatility using OHLC data
- Most efficient estimator for daily data
- Formula: σ = √(1/n × Σ[0.5×ln(H/L)² - (2ln(2)-1)×ln(C/O)²]) × √252
- Handle overnight gaps appropriately

**FR-4: Realized Volatility - Yang-Zhang**
- Calculate volatility accounting for overnight jumps
- Best estimator when overnight moves are significant
- Combines overnight, open-to-close, and Rogers-Satchell components
- Recommended for stocks with significant pre/post-market activity

**FR-5: Implied Volatility Extraction**
- Extract ATM implied volatility from options chain data
- Interpolate IV for exact ATM strike if not available
- Support IV extraction for specific expirations
- Calculate IV term structure across expirations

**FR-6: Volatility Blending**
- Combine realized and implied volatility with configurable weights
- Default blend: 30% RV(20d) + 20% RV(60d) + 50% IV(ATM)
- Allow user override of blending weights
- Provide rationale for recommended blend

**FR-7: Volatility Regime Detection**
- Classify current volatility regime (Low/Normal/High/Extreme)
- Compare current vol to historical percentiles
- Adjust recommendations based on regime
- Alert when regime change detected

### 3.2 Strike Selection

**FR-8: Standard Deviation Strike Calculation**
- Calculate strike price at N standard deviations from current price
- Formula: K = S × exp(n × σ × √T)
- Support both call (positive n) and put (negative n) strikes
- Account for time to expiration in days

**FR-9: Strike Rounding**
- Round calculated strike to nearest tradeable strike
- Support different strike increments ($0.50, $1.00, $2.50, $5.00)
- Prefer rounding direction based on strategy (conservative = round up for calls)
- Return both theoretical and tradeable strikes

**FR-10: Assignment Probability Estimation**
- Calculate P(ITM at expiration) for each strike
- Use Black-Scholes N(-d2) approximation
- Provide delta as proxy for instantaneous assignment probability
- Support Monte Carlo simulation for more accurate estimates (optional)

**FR-11: Strike Profile Selection**
- Provide preset strike profiles with standard deviations:
  - Aggressive: 0.5-1.0σ OTM (30-40% P(ITM))
  - Moderate: 1.0-1.5σ OTM (15-30% P(ITM))
  - Conservative: 1.5-2.0σ OTM (7-15% P(ITM))
  - Defensive: 2.0-2.5σ OTM (2-7% P(ITM))
- Allow custom σ input

**FR-12: Multi-Strike Recommendations**
- Return array of candidate strikes with metrics
- Include: strike, σ distance, delta, P(ITM), premium estimate
- Sort by user preference (income, safety, or balanced)
- Filter by liquidity (open interest, bid-ask spread)

### 3.3 Ladder Strategy

**FR-13: Weekly Expiration Detection**
- Identify next N weekly expirations from options chain
- Handle standard weekly options (Friday expiry)
- Handle Wednesday/Monday weeklies if present
- Skip expirations with earnings dates

**FR-14: Position Allocation**
- Distribute total shares across N weeks
- Support equal allocation (100/N shares per week)
- Support front-weighted allocation (more in near-term)
- Support back-weighted allocation (more in far-term)
- Ensure allocations sum to total position size

**FR-15: Strike Adjustment by Week**
- Adjust σ distance based on time to expiration
- Near-term (Week 1): Slightly more aggressive (n - 0.25σ)
- Mid-term (Week 2-3): Baseline σ
- Far-term (Week 4): Slightly more conservative (n + 0.25σ)
- Rationale: Near-term has accelerating theta, less time for adverse moves

**FR-16: Ladder Output**
- Return complete ladder specification:
  - Expiration date
  - Recommended strike
  - Number of contracts
  - Expected premium (bid price × contracts × 100)
  - Assignment probability
  - Max profit (premium only) and max profit (with appreciation)

### 3.4 Risk Analysis

**FR-17: Income Metrics**
- Calculate annualized yield: (Premium / Stock Price) × (365 / DTE)
- Calculate return if flat: Premium / Stock Price
- Calculate return if called: (Premium + (Strike - Stock Price)) / Stock Price
- Calculate breakeven: Stock Price - Premium

**FR-18: Risk Metrics**
- Calculate expected value: P(OTM) × Premium - P(ITM) × Opportunity Cost
- Estimate opportunity cost of assignment (requires price target input)
- Calculate risk-adjusted return (Sharpe-like ratio for premium income)
- Provide downside protection (breakeven as % below current price)

**FR-19: Scenario Analysis**
- Calculate outcomes at various price points
- Show P&L at: -10%, -5%, ATM, Strike, +5%, +10%
- Compare to buy-and-hold and cash-secured scenarios
- Support custom scenario inputs

### 3.5 Data Integration

**FR-20: Price Data Interface**
- Accept daily OHLC data in standard format
- Support pandas DataFrame input
- Support list of dictionaries input
- Validate data completeness and quality

**FR-21: Options Chain Interface**
- Accept options chain from existing Finnhub module
- Extract relevant strikes and expirations
- Extract IV from chain data
- Validate chain data freshness

**FR-22: Historical Price Data Retrieval**
- Fetch OHLC candle data from Finnhub `/api/v1/stock/candle` endpoint
- Support configurable lookback periods (20, 60, 252 days)
- Handle resolution parameter (daily = "D")
- Parse Finnhub's array format (`t`, `o`, `h`, `l`, `c`, `v`) into standard OHLC structure
- Cache data to minimize API calls and respect rate limits
- Validate data completeness (handle missing days, market holidays)
- Convert Unix timestamps to ISO date format
- Handle API errors gracefully (rate limits, invalid symbols)

**FR-23: Corporate Events Integration**
- Accept earnings date calendar
- Flag expirations that span earnings
- Warn user of elevated risk around events
- Optionally exclude earnings weeks from ladder

---

## 4. Non-Functional Requirements

### 4.1 Performance

**NFR-1: Calculation Speed**
- Volatility calculation: <100ms for 252 days of data
- Strike optimization: <50ms per ticker
- Full ladder generation: <200ms
- Batch processing: >10 tickers/second

**NFR-2: Memory Efficiency**
- Memory usage: <50MB for single ticker analysis
- Support streaming calculation for large datasets
- No memory leaks in long-running processes

**NFR-3: Numerical Precision**
- Volatility: 4 decimal places (e.g., 0.2534 = 25.34%)
- Strike prices: 2 decimal places
- Probabilities: 4 decimal places
- Use Decimal type for currency calculations where needed

### 4.2 Reliability

**NFR-4: Input Validation**
- Validate all input data types and ranges
- Reject invalid data with clear error messages
- Handle edge cases (zero prices, negative values)

**NFR-5: Numerical Stability**
- Handle extreme volatility values (0% to 500%)
- Handle very small/large stock prices
- Avoid division by zero and overflow conditions
- Use numerically stable algorithms

**NFR-6: Graceful Degradation**
- Return partial results if some calculations fail
- Fall back to simpler methods if advanced methods fail
- Log warnings for degraded operation

### 4.3 Maintainability

**NFR-7: Code Quality**
- PEP 8 compliant
- Type hints for all public functions
- Docstrings with examples for all public functions
- Pylint score >9.0

**NFR-8: Testing**
- Unit test coverage >90%
- Integration tests with sample data
- Property-based tests for mathematical functions
- Benchmark tests for performance validation

**NFR-9: Documentation**
- API reference documentation
- Mathematical methodology document
- Usage examples for all features
- Jupyter notebook tutorials

### 4.4 Extensibility

**NFR-10: Modular Design**
- Volatility calculators as pluggable components
- Strike selectors as strategy pattern
- Easy to add new volatility estimators
- Support for alternative data sources

**NFR-11: Configuration**
- All parameters configurable via dataclass
- Support configuration files (YAML/JSON)
- Environment variable overrides
- Sensible defaults for all parameters

---

## 5. Technical Specifications

### 5.1 Data Requirements

#### 5.1.1 Historical Price Data

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| date | datetime | Yes | Trading date |
| open | float | Yes* | Opening price |
| high | float | Yes* | Daily high |
| low | float | Yes* | Daily low |
| close | float | Yes | Closing price |
| adj_close | float | No | Split/dividend adjusted close |
| volume | int | No | Trading volume |

*Required for Parkinson, Garman-Klass, Yang-Zhang estimators

**Data Window Requirements:**

| Window | Days | Purpose |
|--------|------|---------|
| Minimum | 20 | Short-term realized volatility |
| Recommended | 60 | Standard volatility calculation |
| Extended | 252 | Full year for regime comparison |
| Maximum | 504 | Two years for percentile ranking |

**Resolution:** Daily (intraday not required for weekly options)

#### 5.1.2 Options Chain Data

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| expiration_date | str | Yes | Option expiration (YYYY-MM-DD) |
| strike | float | Yes | Strike price |
| option_type | str | Yes | "Call" or "Put" |
| bid | float | Yes | Current bid price |
| ask | float | Yes | Current ask price |
| last | float | No | Last traded price |
| volume | int | No | Daily volume |
| open_interest | int | Yes | Open interest (liquidity) |
| implied_volatility | float | Yes* | IV from market maker |
| delta | float | No | Option delta |

*Required for IV-based calculations

#### 5.1.3 Current Market Data

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| current_price | float | Yes | Current stock price |
| timestamp | datetime | Yes | Price timestamp |

#### 5.1.4 Corporate Events (Optional)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| earnings_date | datetime | No | Next earnings announcement |
| ex_dividend_date | datetime | No | Next ex-dividend date |
| dividend_amount | float | No | Expected dividend |

### 5.2 API Specifications

#### 5.2.1 Volatility Calculator API

```python
class VolatilityCalculator:
    """Calculate various volatility measures from price data."""
    
    def __init__(self, config: VolatilityConfig = None):
        """Initialize with optional configuration."""
        
    def calculate_close_to_close(
        self,
        prices: List[float],
        window: int = 20,
        annualize: bool = True
    ) -> VolatilityResult:
        """
        Calculate close-to-close realized volatility.
        
        Args:
            prices: List of closing prices (oldest to newest)
            window: Lookback window in trading days
            annualize: If True, multiply by √252
            
        Returns:
            VolatilityResult with volatility and metadata
        """
        
    def calculate_parkinson(
        self,
        highs: List[float],
        lows: List[float],
        window: int = 20,
        annualize: bool = True
    ) -> VolatilityResult:
        """Calculate Parkinson (high-low) volatility."""
        
    def calculate_garman_klass(
        self,
        opens: List[float],
        highs: List[float],
        lows: List[float],
        closes: List[float],
        window: int = 20,
        annualize: bool = True
    ) -> VolatilityResult:
        """Calculate Garman-Klass volatility."""
        
    def calculate_yang_zhang(
        self,
        opens: List[float],
        highs: List[float],
        lows: List[float],
        closes: List[float],
        window: int = 20,
        annualize: bool = True
    ) -> VolatilityResult:
        """Calculate Yang-Zhang volatility."""
        
    def calculate_blended(
        self,
        price_data: PriceData,
        implied_volatility: float,
        weights: BlendWeights = None
    ) -> VolatilityResult:
        """
        Calculate blended volatility estimate.
        
        Default weights:
        - 30% realized vol (20-day)
        - 20% realized vol (60-day)
        - 50% implied volatility
        """
```

#### 5.2.2 Strike Optimizer API

```python
class StrikeOptimizer:
    """Calculate optimal strike prices for covered calls."""
    
    def __init__(self, config: StrikeConfig = None):
        """Initialize with optional configuration."""
        
    def calculate_strike_at_sigma(
        self,
        current_price: float,
        volatility: float,
        sigma_distance: float,
        days_to_expiry: int
    ) -> StrikeResult:
        """
        Calculate strike price at N standard deviations.
        
        Args:
            current_price: Current stock price
            volatility: Annualized volatility (decimal, e.g., 0.25 for 25%)
            sigma_distance: Number of standard deviations OTM
            days_to_expiry: Days until option expiration
            
        Returns:
            StrikeResult with theoretical and rounded strikes
        """
        
    def calculate_assignment_probability(
        self,
        current_price: float,
        strike: float,
        volatility: float,
        days_to_expiry: int,
        risk_free_rate: float = 0.05
    ) -> ProbabilityResult:
        """
        Calculate probability of assignment at expiration.
        
        Uses Black-Scholes N(-d2) for P(S_T > K).
        """
        
    def get_strike_recommendations(
        self,
        current_price: float,
        volatility: float,
        days_to_expiry: int,
        options_chain: List[OptionContract],
        profile: StrikeProfile = StrikeProfile.MODERATE,
        min_open_interest: int = 100,
        max_bid_ask_spread: float = 0.10
    ) -> List[StrikeRecommendation]:
        """
        Get ranked strike recommendations with full metrics.
        
        Returns strikes filtered by liquidity, sorted by profile preference.
        """
```

#### 5.2.3 Ladder Builder API

```python
class LadderBuilder:
    """Build laddered covered call positions across expirations."""
    
    def __init__(self, config: LadderConfig = None):
        """Initialize with optional configuration."""
        
    def build_ladder(
        self,
        symbol: str,
        total_shares: int,
        current_price: float,
        volatility: float,
        options_chain: OptionsChain,
        num_weeks: int = 3,
        profile: StrikeProfile = StrikeProfile.MODERATE,
        allocation_strategy: AllocationStrategy = AllocationStrategy.EQUAL,
        exclude_earnings: bool = True,
        earnings_date: Optional[datetime] = None
    ) -> LadderResult:
        """
        Build complete ladder specification.
        
        Args:
            symbol: Stock ticker
            total_shares: Total shares to write against
            current_price: Current stock price
            volatility: Blended volatility estimate
            options_chain: Full options chain data
            num_weeks: Number of weeks to ladder (1-4)
            profile: Strike selection profile
            allocation_strategy: How to distribute across weeks
            exclude_earnings: Skip expirations through earnings
            earnings_date: Next earnings date if known
            
        Returns:
            LadderResult with complete position specifications
        """
        
    def get_weekly_expirations(
        self,
        options_chain: OptionsChain,
        num_weeks: int,
        exclude_dates: List[datetime] = None
    ) -> List[datetime]:
        """Get next N weekly expiration dates."""
```

### 5.3 Data Models

```python
@dataclass
class VolatilityConfig:
    """Configuration for volatility calculations."""
    short_window: int = 20
    long_window: int = 60
    annualization_factor: float = 252.0
    min_data_points: int = 10
    
@dataclass
class BlendWeights:
    """Weights for blended volatility calculation."""
    realized_short: float = 0.30
    realized_long: float = 0.20
    implied: float = 0.50
    
    def __post_init__(self):
        total = self.realized_short + self.realized_long + self.implied
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Weights must sum to 1.0, got {total}")

@dataclass
class VolatilityResult:
    """Result of volatility calculation."""
    volatility: float  # Annualized, decimal (0.25 = 25%)
    method: str  # "close_to_close", "parkinson", etc.
    window: int  # Days used in calculation
    data_points: int  # Actual data points used
    start_date: str  # First date in window
    end_date: str  # Last date in window
    annualized: bool  # Whether result is annualized
    
@dataclass
class StrikeResult:
    """Result of strike calculation."""
    theoretical_strike: float  # Exact calculated strike
    tradeable_strike: float  # Rounded to available strike
    sigma_distance: float  # Actual σ distance of tradeable strike
    current_price: float
    volatility: float
    days_to_expiry: int
    
@dataclass
class ProbabilityResult:
    """Assignment probability calculation result."""
    probability_itm: float  # P(S_T > K) at expiration
    delta: float  # Instantaneous probability proxy
    d1: float  # Black-Scholes d1
    d2: float  # Black-Scholes d2
    
@dataclass 
class StrikeRecommendation:
    """Complete strike recommendation with metrics."""
    strike: float
    expiration_date: str
    sigma_distance: float
    probability_itm: float
    delta: float
    bid: float
    ask: float
    mid_price: float
    open_interest: int
    annualized_yield: float  # Premium / Price × (365/DTE)
    return_if_flat: float  # Premium / Price
    return_if_called: float  # (Premium + Strike - Price) / Price
    breakeven: float  # Price - Premium
    liquidity_score: float  # 0-1 based on OI and spread
    
@dataclass
class LadderLeg:
    """Single leg of a laddered position."""
    expiration_date: str
    days_to_expiry: int
    strike: float
    sigma_distance: float
    num_contracts: int
    num_shares: int  # contracts × 100
    bid: float
    expected_premium: float  # bid × contracts × 100
    probability_itm: float
    annualized_yield: float
    
@dataclass
class LadderResult:
    """Complete ladder specification."""
    symbol: str
    current_price: float
    volatility_used: float
    total_shares: int
    total_contracts: int
    legs: List[LadderLeg]
    total_expected_premium: float
    weighted_avg_sigma: float
    weighted_avg_prob_itm: float
    weighted_avg_yield: float
    generated_at: str

class StrikeProfile(Enum):
    """Preset strike selection profiles."""
    AGGRESSIVE = "aggressive"  # 0.5-1.0σ, 30-40% P(ITM)
    MODERATE = "moderate"  # 1.0-1.5σ, 15-30% P(ITM)
    CONSERVATIVE = "conservative"  # 1.5-2.0σ, 7-15% P(ITM)
    DEFENSIVE = "defensive"  # 2.0-2.5σ, 2-7% P(ITM)
    CUSTOM = "custom"  # User-specified σ

class AllocationStrategy(Enum):
    """How to distribute shares across ladder weeks."""
    EQUAL = "equal"  # Even distribution
    FRONT_WEIGHTED = "front_weighted"  # More in near-term
    BACK_WEIGHTED = "back_weighted"  # More in far-term
```

### 5.4 Mathematical Formulas

#### 5.4.1 Volatility Estimators

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

#### 5.4.2 Strike Calculation

**Strike at N sigma:**
$$K = S \times e^{n \times \sigma \times \sqrt{T}}$$
where:
- $S$ = current stock price
- $n$ = number of standard deviations
- $\sigma$ = annualized volatility
- $T$ = time to expiration in years

#### 5.4.3 Assignment Probability (Black-Scholes)

$$P(S_T > K) = N(-d_2)$$

where:
$$d_1 = \frac{\ln(S/K) + (r + \sigma^2/2)T}{\sigma\sqrt{T}}$$
$$d_2 = d_1 - \sigma\sqrt{T}$$

---

## 6. Implementation Phases

### Phase 1: Core Volatility Module
- ☑ Close-to-close volatility calculator
- ☑ Parkinson volatility calculator
- ☑ Garman-Klass volatility calculator
- ☑ Yang-Zhang volatility calculator
- ☑ Volatility blending logic
- ☑ Unit tests for all calculators (33 tests, 91% coverage)
- ☑ API documentation
- ☑ Integration helpers (IV extraction, term structure)
- ☐ Historical price data retrieval from Finnhub
- ☐ Price data caching mechanism
- ☐ End-to-end volatility calculation with live data

### Phase 2: Strike Optimization
- ☐ Strike-at-sigma calculator
- ☐ Strike rounding to tradeable strikes
- ☐ Assignment probability calculator
- ☐ Strike profile presets
- ☐ Liquidity filtering
- ☐ Strike recommendation engine

### Phase 3: Ladder Builder
- ☐ Weekly expiration detection
- ☐ Position allocation strategies
- ☐ Strike adjustment by week
- ☐ Complete ladder generation
- ☐ Earnings avoidance logic

### Phase 4: Risk Analysis
- ☐ Income metrics calculation
- ☐ Risk metrics calculation
- ☐ Scenario analysis engine
- ☐ Comparison to alternatives

### Phase 5: Integration & Polish
- ☐ Integration with existing Finnhub module
- ☐ Configuration management
- ☐ Comprehensive documentation
- ☐ Example notebooks
- ☐ Performance optimization

---

## 7. Risk Assessment

### 7.1 Model Risk

**Risk**: Volatility estimates may not accurately predict future moves
**Impact**: Strikes selected may result in unexpected assignment rates
**Mitigation**: 
- Use blended volatility (realized + implied)
- Provide confidence intervals
- Recommend conservative profiles for uncertain regimes
- Backtest recommendations against historical data

### 7.2 Data Quality Risk

**Risk**: Finnhub data may be stale or inaccurate
**Impact**: IV extraction may be wrong, strikes may be illiquid
**Mitigation**:
- Validate data freshness (timestamp checks)
- Filter by open interest and spread
- Cross-reference IV with realized vol for sanity
- Document data limitations clearly

### 7.3 Execution Risk

**Risk**: Recommended strikes may not be filled at expected prices
**Impact**: Actual premium income differs from estimates
**Mitigation**:
- Use bid price (not mid) for premium estimates
- Apply slippage factor for wide spreads
- Recommend only liquid strikes (OI > threshold)
- Note spread as percentage of premium

### 7.4 Event Risk

**Risk**: Earnings, dividends, or other events cause outsized moves
**Impact**: Assignment probability much higher than estimated
**Mitigation**:
- Flag earnings dates in recommendations
- Exclude earnings weeks from ladder by default
- Increase σ distance around known events
- Warn user of elevated IV (potential event)

### 7.5 Regime Change Risk

**Risk**: Volatility regime shifts between calculation and expiration
**Impact**: All probability estimates become invalid
**Mitigation**:
- Monitor volatility regime indicators
- Alert on significant vol changes
- Recommend shorter durations in high-vol regimes
- Suggest position adjustment triggers

---

## 8. Acceptance Criteria

### 8.1 Volatility Module

| # | Criterion | Verification |
|---|-----------|--------------|
| AC-1 | Calculate close-to-close vol within 1% of benchmark | Compare to Yahoo Finance/Bloomberg |
| AC-2 | Calculate Parkinson vol from OHLC data | Unit test with known inputs |
| AC-3 | Calculate Garman-Klass vol from OHLC data | Unit test with known inputs |
| AC-4 | Calculate Yang-Zhang vol from OHLC data | Unit test with known inputs |
| AC-5 | Blend volatilities with configurable weights | Unit test weight combinations |
| AC-6 | Handle missing data gracefully | Test with gaps in price series |
| AC-7 | Return consistent results for same inputs | Determinism test |

### 8.2 Strike Optimizer

| # | Criterion | Verification |
|---|-----------|--------------|
| AC-8 | Calculate strike at N sigma accurately | Mathematical verification |
| AC-9 | Round to nearest tradeable strike | Test against options chain |
| AC-10 | Calculate assignment probability correctly | Compare to option delta |
| AC-11 | Filter by liquidity thresholds | Test with varying OI/spread |
| AC-12 | Return ranked recommendations | Verify sorting logic |

### 8.3 Ladder Builder

| # | Criterion | Verification |
|---|-----------|--------------|
| AC-13 | Identify correct weekly expirations | Test against known chain |
| AC-14 | Allocate shares correctly across weeks | Sum to total shares |
| AC-15 | Adjust sigma by week appropriately | Verify near<mid<far |
| AC-16 | Exclude earnings weeks when configured | Test with earnings date |
| AC-17 | Generate complete ladder specification | All fields populated |

### 8.4 Integration

| # | Criterion | Verification |
|---|-----------|--------------|
| AC-18 | Accept price data in standard formats | Test DataFrame and dict |
| AC-19 | Accept existing OptionsChain model | Integration test |
| AC-20 | Fetch historical price data from Finnhub | Test with known ticker |
| AC-21 | Parse Finnhub candle format correctly | Validate OHLC structure |
| AC-22 | Handle missing data and holidays | Test with gaps in data |
| AC-23 | Cache price data appropriately | Verify cache hit/miss |
| AC-24 | Complete calculation in <500ms | Performance test |
| AC-25 | All public functions documented | Docstring coverage |
| AC-26 | Unit test coverage >90% | Coverage report |

---

## 9. Appendix

### A. Glossary

| Term | Definition |
|------|------------|
| **Realized Volatility (RV)** | Historical volatility calculated from past price movements |
| **Implied Volatility (IV)** | Market's expectation of future volatility, derived from option prices |
| **ATM (At-the-Money)** | Option with strike price equal to current stock price |
| **OTM (Out-of-the-Money)** | Call with strike above current price; put with strike below |
| **ITM (In-the-Money)** | Call with strike below current price; put with strike above |
| **Sigma (σ)** | Standard deviation; used as unit of price movement |
| **Delta** | Option sensitivity to stock price; approximates P(ITM) |
| **Assignment** | Exercise of option by buyer, requiring seller to fulfill contract |
| **Ladder** | Distribution of positions across multiple expirations |
| **DTE** | Days to expiration |
| **Annualized** | Scaled to annual basis using √252 trading days |

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

### D. References

- Hull, J. "Options, Futures, and Other Derivatives" - Volatility estimation
- Taleb, N. "Dynamic Hedging" - Practical volatility measurement
- Natenberg, S. "Option Volatility and Pricing" - IV analysis
- Yang, D. & Zhang, Q. (2000) "Drift Independent Volatility Estimation"
- Garman, M. & Klass, M. (1980) "On the Estimation of Security Price Volatilities"
- Parkinson, M. (1980) "The Extreme Value Method for Estimating the Variance"
- Finnhub API Documentation: https://finnhub.io/docs/api

---

## 10. Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-14 | Stock Quant | Initial draft |

---

**Approval Sign-off**

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Product Owner | | | |
| Technical Lead | | | |
| QA Lead | | | |
