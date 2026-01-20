# Implementation Plan
## Covered Options Strategy Optimization System

**Version:** 1.5
**Date:** January 20, 2026
**Status:** Active

---

## Overview

This document tracks the implementation progress of the Covered Options Strategy Optimization System. It maps PRD requirements to sprint-sized work packages and tracks completion status.

---

## Implementation Status Summary

| Phase | Description | Status | Progress |
|-------|-------------|--------|----------|
| Phase 1 | Core Data Infrastructure | ✅ Complete | 100% |
| Phase 2 | Volatility Engine | ✅ Complete | 100% |
| Phase 3 | Alpha Vantage Integration & Caching | ✅ Complete | 100% |
| Phase 4 | Strike Optimization | ✅ Complete | 100% |
| Phase 5 | Covered Options Strategies | ✅ Complete | 100% |
| Phase 6 | Weekly Overlay Scanner & Broker Workflow | ✅ Complete | 100% |
| Phase 7 | Ladder Builder | ✅ Complete | 100% |
| Phase 8 | Risk Analysis & Polish | ⬜ Not Started | 0% |

---

## Sprint Breakdown

### Sprint 1: Phase 3 Completion - Alpha Vantage & Caching ✅ COMPLETE

**Goal**: Complete Alpha Vantage integration with TIME_SERIES_DAILY_ADJUSTED and implement file-based caching.

#### S1.1: Upgrade Alpha Vantage to TIME_SERIES_DAILY_ADJUSTED (3 pts) ✅
- [x] **S1.1.1**: Update `AlphaVantagePriceDataFetcher` to use `TIME_SERIES_DAILY_ADJUSTED` endpoint
- [x] **S1.1.2**: Parse adjusted close, dividend, and split coefficient from response
- [x] **S1.1.3**: Extend `PriceData` dataclass with `adjusted_closes`, `dividends`, `split_coefficients`
- [x] **S1.1.4**: Add unit tests for new parsing logic
- [x] **S1.1.5**: Update `example_end_to_end.py` to display dividend/split data

**PRD Requirements**: FR-7, FR-8

#### S1.2: Local File-Based Cache Implementation (3 pts) ✅
- [x] **S1.2.1**: Create `src/cache.py` with `LocalFileCache` class
- [x] **S1.2.2**: Implement cache key sanitization and file path management
- [x] **S1.2.3**: Implement `get()` method with TTL validation
- [x] **S1.2.4**: Implement `set()` method with JSON serialization
- [x] **S1.2.5**: Implement `delete()` and `clear_all()` methods
- [x] **S1.2.6**: Add configurable cache directory (default: `cache/` in project root)
- [x] **S1.2.7**: Add unit tests for all cache operations (achieved: 88% coverage)

**PRD Requirements**: FR-10, FR-11, FR-12

#### S1.3: API Usage Tracking (2 pts) ✅
- [x] **S1.3.1**: Add Alpha Vantage daily usage tracking to cache module
- [x] **S1.3.2**: Implement `get_alpha_vantage_usage_today()` method
- [x] **S1.3.3**: Implement `increment_alpha_vantage_usage()` method
- [x] **S1.3.4**: Add usage check before API calls with clear warnings
- [x] **S1.3.5**: Create `AlphaVantageRateLimitError` exception
- [x] **S1.3.6**: Add `get_usage_status()` method for monitoring

**PRD Requirements**: FR-8, FR-9

---

### Sprint 2: Phase 4 - Strike Optimization (Est. 10 story points) ✅ COMPLETE

**Goal**: Implement complete strike optimization module with sigma-based calculations and assignment probability.

#### S2.1: Strike-at-Sigma Calculator (3 pts) ✅
- [x] **S2.1.1**: Create `src/strike_optimizer.py` module
- [x] **S2.1.2**: Implement `StrikeOptimizer` class
- [x] **S2.1.3**: Implement `calculate_strike_at_sigma()` method using formula: K = S × exp(n × σ × √T)
- [x] **S2.1.4**: Support both call (positive n) and put (negative n) strikes
- [x] **S2.1.5**: Create `StrikeResult` dataclass for results
- [x] **S2.1.6**: Add unit tests with mathematical verification

**PRD Requirements**: FR-22

#### S2.2: Strike Rounding to Tradeable Strikes (2 pts) ✅
- [x] **S2.2.1**: Implement `round_to_tradeable_strike()` method
- [x] **S2.2.2**: Support different strike increments ($0.50, $1.00, $2.50, $5.00)
- [x] **S2.2.3**: Implement conservative rounding (calls: round up, puts: round down)
- [x] **S2.2.4**: Integration with options chain for available strikes
- [x] **S2.2.5**: Unit tests for rounding logic

**PRD Requirements**: FR-23

#### S2.3: Assignment Probability Calculator (3 pts) ✅
- [x] **S2.3.1**: Implement `calculate_assignment_probability()` method
- [x] **S2.3.2**: Implement finish ITM probability with explicit convention (default: calls N(d2), puts N(-d2)); add regression tests to prevent sign inversion; expose both p_itm_model and delta_chain
- [x] **S2.3.3**: Create `_norm_cdf()` helper using `math.erf`
- [x] **S2.3.4**: Return delta as proxy for instantaneous probability
- [x] **S2.3.5**: Create `ProbabilityResult` dataclass
- [x] **S2.3.6**: Validate against option chain delta values

**PRD Requirements**: FR-24

#### S2.4: Strike Profile Presets and Recommendations (2 pts) ✅
- [x] **S2.4.1**: Create `StrikeProfile` enum (Aggressive, Moderate, Conservative, Defensive)
- [x] **S2.4.2**: Define sigma ranges for each profile:
  - Aggressive: 0.5-1.0σ (30-40% P(ITM))
  - Moderate: 1.0-1.5σ (15-30% P(ITM))
  - Conservative: 1.5-2.0σ (7-15% P(ITM))
  - Defensive: 2.0-2.5σ (2-7% P(ITM))
- [x] **S2.4.3**: Implement `get_strike_recommendations()` method
- [x] **S2.4.4**: Add liquidity filtering (OI > threshold, spread < threshold)
- [x] **S2.4.5**: Return ranked recommendations with full metrics

**PRD Requirements**: FR-25, FR-26

---

### Sprint 3: Phase 5 - Covered Options Strategies (Est. 8 story points) ✅ COMPLETE

**Goal**: Implement covered call, covered put, and wheel strategy support.

#### S3.1: Covered Call Analysis (3 pts) ✅
- [x] **S3.1.1**: Create `src/covered_strategies.py` module
- [x] **S3.1.2**: Implement `CoveredCallAnalyzer` class
- [x] **S3.1.3**: Identify OTM call strikes above current price
- [x] **S3.1.4**: Calculate premium income (bid prices)
- [x] **S3.1.5**: Calculate returns: if flat, if called, breakeven
- [x] **S3.1.6**: Integrate with strike optimizer for recommendations
- [x] **S3.1.7**: Flag wide bid-ask spreads (>10% of premium)
- [x] **S3.1.8**: Warn if expiration spans earnings date
- [x] **S3.1.9**: Create `CoveredCallResult` dataclass

**PRD Requirements**: FR-27, FR-28

#### S3.2: Covered Put Analysis (3 pts) ✅
- [x] **S3.2.1**: Implement `CoveredPutAnalyzer` class
- [x] **S3.2.2**: Identify OTM put strikes below current price
- [x] **S3.2.3**: Calculate collateral requirement (strike × 100)
- [x] **S3.2.4**: Calculate returns: if OTM (premium), if assigned (effective purchase price)
- [x] **S3.2.5**: Flag early assignment risk for deep ITM puts near ex-dividend
- [x] **S3.2.6**: Warn if expiration spans earnings or ex-dividend date
- [x] **S3.2.7**: Create `CoveredPutResult` dataclass

**PRD Requirements**: FR-29, FR-30, FR-31

#### S3.3: Wheel Strategy Support (2 pts) ✅
- [x] **S3.3.1**: Implement `WheelStrategy` class
- [x] **S3.3.2**: Track current state: Cash (sell puts) vs. Shares (sell calls)
- [x] **S3.3.3**: Recommend appropriate strategy based on current holdings
- [x] **S3.3.4**: Calculate cycle metrics (total premium, average cost basis)
- [x] **S3.3.5**: Create `WheelState` and `WheelRecommendation` dataclasses

**PRD Requirements**: FR-32, FR-33

---



### Sprint 4: Phase 6 - Weekly Overlay Scanner & Broker Workflow (Est. 10 story points) ✅ COMPLETE

**Goal**: Deliver holdings-driven weekly covered-call overlay recommendations sized by overwrite cap (default 25%), ranked by net credit after costs, with earnings-week exclusion by default and broker-first execution artifacts.

#### S4.1: Holdings Input & Overwrite Sizing (2 pts) ✅
- [x] **S4.1.1**: Add `Holding` model (`symbol`, `shares`, optional tax fields)
- [x] **S4.1.2**: Add `overwrite_cap_pct` config (default 25%)
- [x] **S4.1.3**: Compute `contracts_to_sell = floor(shares * cap / 100 / 100)`
- [x] **S4.1.4**: Ensure non-actionable positions (0 contracts) are surfaced clearly

#### S4.2: Earnings Exclusion as Hard Gate (2 pts) ✅
- [x] **S4.2.1**: Implement/verify earnings calendar retrieval (Finnhub)
- [x] **S4.2.2**: Add function `expiry_spans_earnings()` and exclude by default
- [x] **S4.2.3**: Add unit/integration tests with mocked earnings dates

#### S4.3: Execution Cost Model (Fees + Slippage) and Net Credit (2 pts) ✅
- [x] **S4.3.1**: Add tunable `per_contract_fee` parameter
- [x] **S4.3.2**: Implement slippage model (default half-spread capped)
- [x] **S4.3.3**: Compute and store `net_credit` and `net_premium_yield`
- [x] **S4.3.4**: Update ranking to use net metrics

#### S4.4: Delta-Band Selection + Tradability Filters (3 pts) ✅
- [x] **S4.4.1**: Add delta-band presets (defensive/conservative/moderate/aggressive)
- [x] **S4.4.2**: Select candidate calls by delta band (primary for weeklies)
- [x] **S4.4.3**: Filter out zero-bid/zero-premium strikes from Top N
- [x] **S4.4.4**: Improve spread filtering with absolute + relative thresholds
- [x] **S4.4.5**: Emit explicit rejection reasons for filtered strikes

#### S4.5: Broker Checklist + LLM Memo Payload (1 pt) ✅
- [x] **S4.5.1**: Generate per-trade broker checklist output
- [x] **S4.5.2**: Emit structured JSON payload for optional LLM memo generation

**PRD Requirements**: FR-42 to FR-50, FR-45, FR-46


### Sprint 5: Phase 7 - Ladder Builder (Est. 8 story points) ✅ COMPLETE

**Goal**: Implement laddered position building across multiple weekly expirations.

#### S5.1: Weekly Expiration Detection (2 pts) ✅
- [x] **S5.1.1**: Create `src/ladder_builder.py` module
- [x] **S5.1.2**: Implement `LadderBuilder` class
- [x] **S5.1.3**: Implement `get_weekly_expirations()` method
- [x] **S5.1.4**: Handle standard weekly options (Friday expiry)
- [x] **S5.1.5**: Handle Wednesday/Monday weeklies if present
- [x] **S5.1.6**: Filter out past expirations

**PRD Requirements**: FR-34

#### S5.2: Position Allocation Strategies (2 pts) ✅
- [x] **S5.2.1**: Create `AllocationStrategy` enum (Equal, FrontWeighted, BackWeighted)
- [x] **S5.2.2**: Implement `calculate_allocations()` method
- [x] **S5.2.3**: Equal: 100/N shares per week
- [x] **S5.2.4**: Front-weighted: More in near-term expirations
- [x] **S5.2.5**: Back-weighted: More in far-term expirations
- [x] **S5.2.6**: Ensure allocations sum to total position size

**PRD Requirements**: FR-35

#### S5.3: Strike Adjustment by Week (2 pts) ✅
- [x] **S5.3.1**: Implement `adjust_sigma_for_week()` method
- [x] **S5.3.2**: Near-term (Week 1): n - 0.25σ (slightly more aggressive)
- [x] **S5.3.3**: Mid-term (Week 2-3): Baseline σ
- [x] **S5.3.4**: Far-term (Week 4+): n + 0.25σ (slightly more conservative)
- [x] **S5.3.5**: Document rationale in code comments

**PRD Requirements**: FR-36

#### S5.4: Complete Ladder Generation (2 pts) ✅
- [x] **S5.4.1**: Implement `build_ladder()` method
- [x] **S5.4.2**: Create `LadderLeg` dataclass with all fields
- [x] **S5.4.3**: Create `LadderResult` dataclass with summary metrics
- [x] **S5.4.4**: Integrate earnings calendar for automatic avoidance
- [x] **S5.4.5**: Return complete ladder specification with warnings
- [x] **S5.4.6**: Calculate aggregate metrics (total premium, weighted averages)

**PRD Requirements**: FR-37, FR-38

---

### Sprint 6: Phase 8 - Risk Analysis & Polish (Est. 10 story points)

**Goal**: Implement income/risk metrics, scenario analysis, and finalize documentation.

#### S6.1: Income Metrics Calculation (2 pts)
- [ ] **S6.1.1**: Create `src/risk_analyzer.py` module
- [ ] **S6.1.2**: Implement `RiskAnalyzer` class
- [ ] **S6.1.3**: Calculate annualized yield: (Premium / Stock Price) × (365 / DTE)
- [ ] **S6.1.4**: Calculate return if flat: Premium / Stock Price
- [ ] **S6.1.5**: Calculate return if called/assigned
- [ ] **S6.1.6**: Calculate breakeven prices

**PRD Requirements**: FR-39

#### S6.2: Risk Metrics Calculation (2 pts)
- [ ] **S6.2.1**: Calculate expected value: P(OTM) × Premium - P(ITM) × Opportunity Cost
- [ ] **S6.2.2**: Implement opportunity cost estimation (with price target input)
- [ ] **S6.2.3**: Calculate risk-adjusted return (Sharpe-like ratio)
- [ ] **S6.2.4**: Calculate downside protection percentage

**PRD Requirements**: FR-40

#### S6.3: Scenario Analysis Engine (2 pts)
- [ ] **S6.3.1**: Implement `calculate_scenarios()` method
- [ ] **S6.3.2**: Calculate outcomes at: -10%, -5%, ATM, Strike, +5%, +10%
- [ ] **S6.3.3**: Compare to buy-and-hold scenarios
- [ ] **S6.3.4**: Support custom scenario inputs
- [ ] **S6.3.5**: Create `ScenarioResult` dataclass

**PRD Requirements**: FR-41

#### S6.4: Earnings Calendar Integration (2 pts)
- [ ] **S6.4.1**: Implement Finnhub earnings calendar retrieval
- [ ] **S6.4.2**: Add to `FinnhubClient.get_earnings_calendar()` method
- [ ] **S6.4.3**: Cache earnings data (weekly refresh)
- [ ] **S6.4.4**: Create `EarningsEvent` dataclass
- [ ] **S6.4.5**: Integrate with ladder builder for earnings avoidance

**PRD Requirements**: FR-3, FR-38

#### S6.5: Documentation & Final Polish (2 pts)
- [ ] **S6.5.1**: Update README with complete setup instructions
- [ ] **S6.5.2**: Create API authentication guide (Finnhub and Alpha Vantage)
- [ ] **S6.5.3**: Ensure all functions have docstrings and type hints
- [ ] **S6.5.4**: Create usage examples for all features
- [ ] **S6.5.5**: Document known limitations and disclaimers
- [ ] **S6.5.6**: Run full test suite and achieve >90% coverage
- [ ] **S6.5.7**: Run ruff check and ensure no errors
- [ ] **S6.5.8**: Performance validation (<500ms for full calculation)

**PRD Requirements**: NFR-11, NFR-12, NFR-13

---

## Completed Work

### Phase 1: Core Data Infrastructure ✅

| Task | Status | Notes |
|------|--------|-------|
| Finnhub API connection and authentication | ✅ | `src/config.py`, `src/finnhub_client.py` |
| Basic options chain retrieval | ✅ | `src/finnhub_client.py` |
| Options chain data parsing | ✅ | `src/options_chain.py`, `src/options_service.py` |
| Error handling with retry logic | ✅ | Exponential backoff implemented |
| Basic documentation and tests | ✅ | Initial tests in place |

### Phase 2: Volatility Engine ✅

| Task | Status | Notes |
|------|--------|-------|
| Close-to-close volatility calculator | ✅ | `src/volatility.py` |
| Parkinson volatility calculator | ✅ | `src/volatility.py` |
| Garman-Klass volatility calculator | ✅ | `src/volatility.py` |
| Yang-Zhang volatility calculator | ✅ | `src/volatility.py` |
| Volatility blending logic | ✅ | `BlendWeights` dataclass |
| Unit tests (33 tests, 91% coverage) | ✅ | `tests/test_volatility.py` |
| Integration helpers | ✅ | `src/volatility_integration.py` |

### Phase 3: Alpha Vantage Integration & Caching ✅

| Task | Status | Notes |
|------|--------|-------|
| Alpha Vantage config class | ✅ | `AlphaVantageConfig` in `src/config.py` |
| Basic price data fetcher | ✅ | `AlphaVantagePriceDataFetcher` in `src/price_fetcher.py` |
| TIME_SERIES_DAILY_ADJUSTED endpoint | ✅ | Returns OHLC + dividends + splits |
| In-memory caching (basic) | ✅ | `PriceDataCache` class |
| File-based cache | ✅ | `LocalFileCache` in `src/cache.py` (88% coverage) |
| API usage tracking | ✅ | Daily limit tracking with warnings |
| PriceData extended | ✅ | Added `adjusted_closes`, `dividends`, `split_coefficients` |
| AlphaVantageRateLimitError | ✅ | Custom exception for rate limits |

---

## Test Coverage Goals

| Module | Current | Target | Notes |
|--------|---------|--------|-------|
| `src/cache.py` | 88% | 95% | LocalFileCache module ✅ |
| `src/config.py` | 55% | 100% | Add Alpha Vantage config tests |
| `src/finnhub_client.py` | 98% | 95% | ✅ Exceeds target |
| `src/models.py` | 100% | 95% | ✅ Exceeds target |
| `src/options_service.py` | 73% | 90% | |
| `src/volatility.py` | 90% | 95% | |
| `src/price_fetcher.py` | 53% | 95% | Needs more tests for new features |
| `src/strike_optimizer.py` | 91% | 90% | ✅ Exceeds target |
| `src/covered_strategies.py` | 87% | 90% | ✅ Near target |
| `src/overlay_scanner.py` | 94% | 90% | ✅ Exceeds target |
| `src/ladder_builder.py` | 91% | 90% | ✅ Exceeds target |
| `src/risk_analyzer.py` | N/A | 90% | Not yet created |
| **Overall** | 76% | **>90%** | 392 tests passing |

---

## Acceptance Criteria Tracking

### Data Infrastructure (AC-1 to AC-8)

| # | Criterion | Status |
|---|-----------|--------|
| AC-1 | Successfully authenticate with Finnhub API | ✅ |
| AC-2 | Successfully authenticate with Alpha Vantage API | ✅ |
| AC-3 | Retrieve options chain data for ticker | ✅ |
| AC-4 | Retrieve historical OHLC data with dividends | ✅ |
| AC-5 | Retrieve earnings calendar | ⬜ |
| AC-6 | Cache data locally and retrieve from cache | ✅ |
| AC-7 | Handle API rate limits gracefully | ✅ |
| AC-8 | Handle API errors with clear messages | ✅ |

### Volatility Module (AC-9 to AC-15)

| # | Criterion | Status |
|---|-----------|--------|
| AC-9 | Calculate close-to-close vol within 1% of benchmark | ✅ |
| AC-10 | Calculate Parkinson vol from OHLC data | ✅ |
| AC-11 | Calculate Garman-Klass vol from OHLC data | ✅ |
| AC-12 | Calculate Yang-Zhang vol from OHLC data | ✅ |
| AC-13 | Blend volatilities with configurable weights | ✅ |
| AC-14 | Handle missing data gracefully | ✅ |
| AC-15 | Return consistent results for same inputs | ✅ |

### Strike Optimizer (AC-16 to AC-21)

| # | Criterion | Status |
|---|-----------|--------|
| AC-16 | Calculate strike at N sigma accurately | ✅ |
| AC-17 | Round to nearest tradeable strike | ✅ |
| AC-18 | Calculate assignment probability (calls) | ✅ |
| AC-19 | Calculate assignment probability (puts) | ✅ |
| AC-20 | Filter by liquidity thresholds | ✅ |
| AC-21 | Return ranked recommendations | ✅ |

### Covered Options Strategies (AC-22 to AC-25)

| # | Criterion | Status |
|---|-----------|--------|
| AC-22 | Generate covered call recommendations | ✅ |
| AC-23 | Generate covered put recommendations | ✅ |
| AC-24 | Calculate collateral requirements for puts | ✅ |
| AC-25 | Flag early assignment risk for puts | ✅ |


### Weekly Overlay Scanner & Broker Workflow (AC-36 to AC-43)

| # | Criterion | Status |
|---|-----------|--------|
| AC-36 | Accept holdings input and compute contracts from overwrite cap | ✅ |
| AC-37 | Exclude earnings-week expirations by default (hard gate) | ✅ |
| AC-38 | Select weekly calls by delta-band presets | ✅ |
| AC-39 | Compute net credit using fee + slippage model | ✅ |
| AC-40 | Filter out zero-bid contracts; enforce spread/OI thresholds | ✅ |
| AC-41 | Emit explicit rejection reasons for filtered strikes | ✅ |
| AC-42 | Output per-trade broker checklist | ✅ |
| AC-43 | Emit structured JSON payload for optional LLM memo | ✅ |

### Ladder Builder (AC-26 to AC-30)

| # | Criterion | Status |
|---|-----------|--------|
| AC-26 | Identify correct weekly expirations | ✅ |
| AC-27 | Allocate shares correctly across weeks | ✅ |
| AC-28 | Adjust sigma by week appropriately | ✅ |
| AC-29 | Exclude earnings weeks when configured | ✅ |
| AC-30 | Generate complete ladder specification | ✅ |

### Integration & Quality (AC-31 to AC-35)

| # | Criterion | Status |
|---|-----------|--------|
| AC-31 | All code documented and type-hinted | ⬜ Partial |
| AC-32 | Unit test coverage >80% | ✅ ~85% |
| AC-33 | Code passes linting (ruff check) | ✅ |
| AC-34 | Complete calculation in <500ms | ⬜ |
| AC-35 | README provides clear setup instructions | ⬜ Partial |

---

## Dependencies & Blockers

| Item | Type | Status | Notes |
|------|------|--------|-------|
| Alpha Vantage API key | Dependency | ✅ | User has key |
| Finnhub API key | Dependency | ✅ | User has key |
| TIME_SERIES_DAILY_ADJUSTED response structure | Dependency | ✅ | Documented in PRD |

---

## Notes

- All tests currently pass (392 tests)
- Basic end-to-end workflow functional (`example_end_to_end.py`)
- Sprint 2 complete: Strike Optimization module with 53 tests
- Sprint 3 complete: Covered Strategies module with 48 tests
- Sprint 4 complete: Overlay Scanner module with 70 tests
- Sprint 5 complete: Ladder Builder module with 40 tests (91% coverage)
- Fixed critical IV conversion bug (Finnhub returns IV as percentage, not decimal)
- Cache system refactored to unified `market_data` table
- Each sprint deliverable should include updated unit tests

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-15 | Software Developer | Initial implementation plan |
| 1.1 | 2026-01-16 | Software Developer | Sprint 1 complete: LocalFileCache, TIME_SERIES_DAILY_ADJUSTED, API usage tracking |
| 1.2 | 2026-01-18 | Software Developer | Sprint 2 complete: StrikeOptimizer module with sigma calculations, assignment probability, and strike recommendations. Fixed IV normalization bug. Cache refactored to unified market_data table. |
| 1.3 | 2026-01-18 | Software Developer | Added Phase 6: Weekly Overlay Scanner & broker-first workflow (overwrite sizing, earnings exclusion hard gate, net-credit ranking, tradability filters, checklist + LLM memo payload). Shifted Ladder to Phase 7 and Risk Analysis to Phase 8. |
| 1.4 | 2026-01-19 | Software Developer | Sprint 4 complete: Overlay Scanner module fully implemented with 70 tests and 94% coverage. All Sprint 4 acceptance criteria met. |
| 1.5 | 2026-01-20 | Software Developer | Sprint 5 complete: Ladder Builder module implemented with 40 tests and 91% coverage. Features: weekly expiration detection (Friday/Wednesday/Monday), allocation strategies (Equal/FrontWeighted/BackWeighted), sigma adjustment by week, earnings integration. All Sprint 5 acceptance criteria met. |
