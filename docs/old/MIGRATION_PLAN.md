# Migration Plan: AlphaVantage & Finnhub → Schwab API

## Executive Summary

This plan outlines the complete migration from AlphaVantage and Finnhub APIs to the Schwab API for the options income trading application. The migration will be executed in 4 phases to minimize risk and ensure continuity of functionality.

**Key Findings:**
- ✅ Schwab API provides **price history** endpoint (replacement for AlphaVantage & Finnhub price data)
- ✅ Schwab API provides **options chain** data (replacement for Finnhub options chains)
- ❌ Schwab API does **NOT** provide **earnings calendar** data
- ✅ **DECISION**: Keep Finnhub for earnings calendar only

---

## Current State Analysis

### AlphaVantage Usage
**Purpose**: Historical daily price data (OHLCV) for volatility calculations

**Implementation**: `/workspaces/options_income/src/alphavantage_client.py`
- `fetch_daily_prices()` - Returns `PriceData` with OHLCV + volume
- Free tier: 25 API calls/day, max 100 data points per request
- 24-hour file-based caching via `LocalFileCache`

**Files Using AlphaVantage** (6 files):
1. `src/price_fetcher.py` - `AlphaVantagePriceDataFetcher` wrapper
2. `src/wheel/manager.py` - Price data for wheel strategy
3. `src/wheel/cli.py` - CLI interface
4. `src/wheel/recommend.py` - Recommendation engine
5. `example_end_to_end.py` - Examples
6. `tests/test_price_fetcher.py` - Tests

**Data Structure Returned**:
```python
@dataclass
class PriceData:
    dates: list[str]              # YYYY-MM-DD
    closes: list[float]           # Required
    opens: Optional[list[float]]
    highs: Optional[list[float]]
    lows: Optional[list[float]]
    volumes: Optional[list[float]]
```

---

### Finnhub Usage
**Purpose**: Options chain data + historical price data (premium) + earnings calendar

**Implementation**: `/workspaces/options_income/src/finnhub_client.py`

**Three Main Methods**:

1. **`get_option_chain(symbol)`** → Used for options scanning
   - Free tier available
   - Returns options contracts with strikes, greeks, IV

2. **`get_candle_data(symbol, lookback_days)`** → Historical OHLC
   - **Premium subscription required** (403 on free tier)
   - Returns `PriceData` object

3. **`get_earnings_calendar(symbol, from_date, to_date)`** → Earnings dates
   - Free tier available
   - Returns list of earnings dates (YYYY-MM-DD format)

**Files Using Finnhub** (11+ core files):
1. `src/options_service.py` - `OptionsChainService` wraps `get_option_chain()`
2. `src/price_fetcher.py` - `PriceDataFetcher` wraps `get_candle_data()`
3. `src/earnings_calendar.py` - `EarningsCalendar` wraps `get_earnings_calendar()`
4. `src/overlay_scanner.py` - Uses earnings exclusion
5. `src/ladder_builder.py` - Uses earnings exclusion
6. `src/main.py` - CLI entry point
7. `src/wheel/manager.py` - Wheel strategy manager
8. `src/wheel/cli.py` - Wheel CLI
9. Tests: `test_finnhub_client.py`, `test_earnings_calendar.py`, `test_options_service.py`
10. Documentation references (10+ files)

---

### Schwab API Capabilities

**✅ Available Capabilities**:

1. **Price History** (via REST API `get_price_history()`)
   - Endpoint: `/marketdata/v1/pricehistory`
   - Parameters: symbol, period_type, period, frequency_type, frequency, start/end dates
   - Returns: OHLC candle data by day/week/minute
   - Rate limit: 120 requests/minute
   - Source: [Web search results](https://rdrr.io/cran/charlesschwabapi/man/get_price_history.html)

2. **Options Chain Data** (already implemented!)
   - Endpoint: `/marketdata/v1/chains`
   - File: `src/schwab/client.py::get_option_chain()`
   - Returns: Fully parsed `OptionsChain` with calls, puts, greeks, IV
   - Features: Strike filtering, date filtering, contract type filtering
   - Cache: 15-minute TTL

3. **Real-time Quotes**
   - Endpoint: `/marketdata/v1/{symbol}/quotes`
   - Already implemented: `src/schwab/client.py::get_quote()`
   - Cache: 5-minute TTL

**❌ NOT Available**:
- **Earnings Calendar**: No earnings calendar endpoint in Schwab API

---

## Migration Strategy

### Phase 1: Migrate AlphaVantage → Schwab Price History

**Goal**: Replace all AlphaVantage price data fetching with Schwab price history endpoint

**Steps**:

1. **Implement Schwab price history method** in `src/schwab/client.py`:
   ```python
   def get_price_history(
       self,
       symbol: str,
       period_type: str = "month",
       period: int = 3,
       frequency_type: str = "daily",
       frequency: int = 1,
       start_date: Optional[datetime] = None,
       end_date: Optional[datetime] = None,
       use_cache: bool = True
   ) -> PriceData
   ```
   - Parse Schwab response into `PriceData` format
   - Add caching support (24-hour TTL matching AlphaVantage)
   - Handle errors, rate limits

2. **Create `SchwabPriceDataFetcher`** in `src/price_fetcher.py`:
   ```python
   class SchwabPriceDataFetcher:
       def __init__(self, schwab_client: SchwabClient, ...):
           ...

       def fetch_price_data(self, symbol: str, lookback_days: int) -> PriceData:
           # Convert lookback_days to Schwab API parameters
           # Call schwab_client.get_price_history()
           # Return PriceData
   ```

3. **Update all AlphaVantage consumers** to use Schwab:
   - `src/wheel/manager.py` - Replace `AlphaVantagePriceDataFetcher` with `SchwabPriceDataFetcher`
   - `src/wheel/cli.py` - Update imports
   - `src/wheel/recommend.py` - Update imports
   - `example_end_to_end.py` - Update examples

4. **Update tests**:
   - `tests/test_price_fetcher.py` - Add Schwab price fetcher tests
   - Mock Schwab price history responses

5. **Add Schwab price history endpoint definition**:
   - `src/schwab/endpoints.py`: Add `MARKETDATA_PRICE_HISTORY = "/marketdata/v1/pricehistory"`

**Files to Modify** (7 files):
- `src/schwab/client.py` (add `get_price_history()`)
- `src/schwab/endpoints.py` (add endpoint constant)
- `src/price_fetcher.py` (add `SchwabPriceDataFetcher`)
- `src/wheel/manager.py` (use Schwab)
- `src/wheel/cli.py` (use Schwab)
- `src/wheel/recommend.py` (use Schwab)
- `tests/test_price_fetcher.py` (add tests)

**Critical Files**:
- `/workspaces/options_income/src/schwab/client.py` - Add price history method
- `/workspaces/options_income/src/price_fetcher.py` - Add Schwab fetcher
- `/workspaces/options_income/src/wheel/manager.py` - Switch to Schwab

---

### Phase 2: Migrate Finnhub Options Chain → Schwab

**Goal**: Replace Finnhub options chain usage with existing Schwab implementation

**Steps**:

1. **Update `OptionsChainService`** in `src/options_service.py`:
   - Replace `FinnhubClient` dependency with `SchwabClient`
   - Update `get_option_chain()` to call `schwab_client.get_option_chain()`
   - Map Schwab's `OptionsChain` model to existing contract format

2. **Update consumers** (5 files):
   - `src/overlay_scanner.py` - Update to use Schwab-backed `OptionsChainService`
   - `src/ladder_builder.py` - Update to use Schwab-backed `OptionsChainService`
   - `src/main.py` - Update imports if needed
   - `src/wheel/manager.py` - Update if using options chains
   - `src/wheel/cli.py` - Update if using options chains

3. **Update tests**:
   - `tests/test_options_service.py` - Update mocks to use Schwab responses
   - Add tests for Schwab options chain parsing

**Files to Modify** (5 files):
- `src/options_service.py` (replace Finnhub with Schwab)
- `src/overlay_scanner.py` (update service usage)
- `src/ladder_builder.py` (update service usage)
- `src/main.py` (update if needed)
- `tests/test_options_service.py` (update tests)

**Critical Files**:
- `/workspaces/options_income/src/options_service.py` - Replace Finnhub with Schwab
- `/workspaces/options_income/src/overlay_scanner.py` - Update service usage

---

### Phase 3: Handle Earnings Calendar (DECISION: Keep Finnhub)

**Goal**: Maintain earnings calendar functionality using Finnhub

**✅ USER DECISION**: **Keep Finnhub for Earnings Calendar Only**

**Rationale**:
- Maintains existing functionality with minimal code changes
- Finnhub earnings calendar is free tier
- No alternative earnings calendar available in Schwab API

**Files Affected**: None (earnings calendar stays as-is)

---

### Phase 4: Cleanup & Documentation

**Goal**: Remove all unused code and update documentation

**Steps**:

1. **Remove AlphaVantage completely**:
   - Delete `src/alphavantage_client.py` (390 lines)
   - Remove from `src/price_fetcher.py`: `AlphaVantagePriceDataFetcher` class
   - Remove from `src/config.py`: `AlphaVantageConfig` dataclass
   - Remove API key references:
     - `.gitignore` entry: `alpha_vantage_api_key.txt`
     - Environment variable: `ALPHA_VANTAGE_API_KEY`

2. **Partial Finnhub Cleanup** (keeping for earnings calendar):
   - **KEEP**: `src/finnhub_client.py` (for earnings calendar)
   - **KEEP**: `src/earnings_calendar.py`
   - **KEEP**: `src/config.py::FinnhubConfig`
   - **KEEP**: `tests/test_finnhub_client.py`
   - **REMOVE from `src/price_fetcher.py`**: `PriceDataFetcher` class (Finnhub price data wrapper)
   - **UPDATE tests**: Ensure earnings calendar tests still pass
   - **UPDATE documentation**: Clarify Finnhub is only used for earnings now

3. **Update requirements.txt**:
   - Remove package dependencies (if no longer needed):
     - AlphaVantage: No external package (uses `requests`)
     - Finnhub: Keep (uses `requests`)

4. **Update documentation** (8+ files):
   - `README.md` - Remove AlphaVantage setup, update Finnhub to "earnings only"
   - `docs/SCHWAB_OAUTH_SETUP.md` - Update to reflect Schwab as primary data provider
   - `docs/oauth_design.md` - Update API integration section
   - `docs/design_wheel_strategy_tool.md` - Update data sources table
   - `docs/IMPLEMENTATION_PLAN.md` - Remove AlphaVantage references
   - `scripts/README.md` - Update if mentions old APIs
   - `scripts/QUICKSTART.md` - Update setup steps
   - `example_end_to_end.py` - Remove AlphaVantage examples

5. **Update configuration**:
   - `src/config.py` - Remove `AlphaVantageConfig`
   - Add Schwab-specific config if needed (rate limits, caching TTL)

**Files to Delete** (1 file):
- `src/alphavantage_client.py`

**Files to Modify** (10+ files):
- `src/price_fetcher.py` (remove AlphaVantage fetcher)
- `src/config.py` (remove AlphaVantage config)
- `README.md`
- `docs/*.md` (8+ documentation files)
- `example_end_to_end.py`

**Critical Files**:
- `/workspaces/options_income/src/config.py` - Remove AlphaVantage config
- `/workspaces/options_income/README.md` - Update setup instructions
- `/workspaces/options_income/docs/design_wheel_strategy_tool.md` - Update architecture

---

## Implementation Order

### Sequential Execution (Recommended)

1. **Phase 1**: AlphaVantage → Schwab (Est: 1-2 days)
   - Lowest risk, single data source migration
   - Validates Schwab price history integration

2. **Phase 2**: Finnhub Options → Schwab (Est: 1 day)
   - Existing Schwab options already implemented
   - Update service wrappers

3. **Phase 3**: Earnings Calendar (Est: 0 days)
   - No action needed (keeping Finnhub)

4. **Phase 4**: Cleanup & Documentation (Est: 1 day)
   - Final cleanup after all migrations complete

**Total Estimated Time**: 3-4 days

---

## Final Migration Summary

### What Gets Removed:
- ✅ **AlphaVantage client** - Completely removed (390 lines)
- ✅ **AlphaVantage config** - Removed from `src/config.py`
- ✅ **AlphaVantagePriceDataFetcher** - Removed from `src/price_fetcher.py`
- ✅ **Finnhub price data usage** - `PriceDataFetcher` class removed
- ✅ **Finnhub options chain usage** - Replaced with Schwab

### What Stays:
- ✅ **Schwab API client** - Primary data source for prices and options
- ✅ **Finnhub client** - Kept for earnings calendar only
- ✅ **Finnhub earnings calendar** - `src/earnings_calendar.py` unchanged
- ✅ **FinnhubConfig** - Kept in `src/config.py`

### New Data Flow:
1. **Price History**: Schwab API → `SchwabPriceDataFetcher` → `PriceData`
2. **Options Chains**: Schwab API → `SchwabClient.get_option_chain()` → `OptionsChain`
3. **Earnings Calendar**: Finnhub API → `EarningsCalendar` → Earnings dates (unchanged)

---

## Success Criteria

### Phase 1 Complete When:
- ✅ Schwab price history endpoint implemented
- ✅ `SchwabPriceDataFetcher` class created
- ✅ All AlphaVantage consumers migrated to Schwab
- ✅ Tests pass with Schwab data
- ✅ Volatility calculations produce same results

### Phase 2 Complete When:
- ✅ `OptionsChainService` uses Schwab client
- ✅ Options scanning works with Schwab data
- ✅ Tests pass with Schwab options chains

### Phase 3 Complete When:
- ✅ Earnings calendar continues working (no changes needed)

### Phase 4 Complete When:
- ✅ AlphaVantage code deleted
- ✅ Finnhub options/price code removed
- ✅ All documentation updated
- ✅ README reflects Schwab as primary provider, Finnhub for earnings only

---

## Verification Plan

### End-to-End Testing
1. **Run wheel strategy CLI**: `python -m src.wheel.cli recommend --symbol AAPL`
   - Should fetch prices from Schwab
   - Should fetch options from Schwab
   - Should filter earnings using Finnhub
   - Should produce recommendations

2. **Check API usage**:
   - Verify Schwab OAuth tokens for price/options
   - Verify Finnhub API used only for earnings calendar

3. **Validate caching**:
   - Check `LocalFileCache` database for Schwab price data
   - Verify 24-hour TTL on price data
   - Verify 15-minute TTL on options chains

---

## Notes

- **Schwab price history endpoint** confirmed available via web search
- **Schwab options chain** already fully implemented in codebase
- **Finnhub earnings calendar** maintained for feature completeness
- **All migrations preserve existing `PriceData` and `OptionsChain` data structures**
- **Caching strategy remains identical** to minimize behavior changes
