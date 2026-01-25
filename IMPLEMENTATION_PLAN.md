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
| Phase 8 | Risk Analysis & Polish | ✅ Complete | 100% |
| Phase 9 | Schwab OAuth Integration | 🔄 In Progress | 0% |

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

### Sprint 6: Phase 8 - Risk Analysis & Polish (Est. 10 story points) ✅ COMPLETE

**Goal**: Implement income/risk metrics, scenario analysis, and finalize documentation.

#### S6.1: Income Metrics Calculation (2 pts) ✅
- [x] **S6.1.1**: Create `src/risk_analyzer.py` module
- [x] **S6.1.2**: Implement `RiskAnalyzer` class
- [x] **S6.1.3**: Calculate annualized yield: (Premium / Stock Price) × (365 / DTE)
- [x] **S6.1.4**: Calculate return if flat: Premium / Stock Price
- [x] **S6.1.5**: Calculate return if called/assigned
- [x] **S6.1.6**: Calculate breakeven prices

**PRD Requirements**: FR-39

#### S6.2: Risk Metrics Calculation (2 pts) ✅
- [x] **S6.2.1**: Calculate expected value: P(OTM) × Premium - P(ITM) × Opportunity Cost
- [x] **S6.2.2**: Implement opportunity cost estimation (with price target input)
- [x] **S6.2.3**: Calculate risk-adjusted return (Sharpe-like ratio)
- [x] **S6.2.4**: Calculate downside protection percentage

**PRD Requirements**: FR-40

#### S6.3: Scenario Analysis Engine (2 pts) ✅
- [x] **S6.3.1**: Implement `calculate_scenarios()` method
- [x] **S6.3.2**: Calculate outcomes at: -20%, -10%, -5%, ATM, Strike, +5%, +10%, +20%
- [x] **S6.3.3**: Compare to buy-and-hold scenarios
- [x] **S6.3.4**: Support custom scenario inputs
- [x] **S6.3.5**: Create `ScenarioResult` dataclass

**PRD Requirements**: FR-41

#### S6.4: Earnings Calendar Integration (2 pts) ✅
- [x] **S6.4.1**: Finnhub earnings calendar retrieval (already implemented)
- [x] **S6.4.2**: `FinnhubClient.get_earnings_calendar()` method (already exists)
- [x] **S6.4.3**: Cache earnings data (24-hour TTL implemented)
- [x] **S6.4.4**: Create `EarningsEvent` dataclass with properties
- [x] **S6.4.5**: Integration with ladder builder (already exists)

**PRD Requirements**: FR-3, FR-38

#### S6.5: Documentation & Final Polish (2 pts) ✅
- [x] **S6.5.1**: Create README.md with complete setup instructions
- [x] **S6.5.2**: API authentication documented in README
- [x] **S6.5.3**: All functions have docstrings and type hints
- [x] **S6.5.4**: Usage examples in README for all features
- [x] **S6.5.5**: Known limitations and disclaimers documented
- [x] **S6.5.6**: Run full test suite - 446 tests, 79% overall (core modules >90%)
- [x] **S6.5.7**: Run ruff check - all checks pass
- [x] **S6.5.8**: Performance validation - 300 calcs in 68ms (< 500ms requirement)

**PRD Requirements**: NFR-11, NFR-12, NFR-13

---

### Sprint 7: Phase 9.1 - OAuth Core Infrastructure (Est. 8 story points) 🔄 IN PROGRESS

**Goal**: Implement core OAuth 2.0 infrastructure for Schwab API integration including configuration, token storage, and token lifecycle management. Architecture must support devcontainer deployment with split execution (host authorization, container application).

#### S7.1: OAuth Configuration Module (2 pts) ⬜
- [ ] **S7.1.1**: Create `src/oauth/` module directory structure
- [ ] **S7.1.2**: Create `src/oauth/config.py` with `SchwabOAuthConfig` dataclass
- [ ] **S7.1.3**: Set default `token_file` to `/workspaces/options_income/.schwab_tokens.json`
- [ ] **S7.1.4**: Implement environment variable loading (`from_env()` classmethod)
- [ ] **S7.1.5**: Add configuration validation (client_id, client_secret, ports, paths)
- [ ] **S7.1.6**: Implement `callback_url` property generation
- [ ] **S7.1.7**: Add support for custom SSL certificate paths (for host execution)
- [ ] **S7.1.8**: Create unit tests for config loading and validation

**Requirements**: FR-O1, FR-O2, FR-O3, FR-O3.1 from oauth_requirements.md
**Dependencies**: None
**Deliverable**: Configuration management with container-compatible paths

#### S7.2: Token Storage Implementation (2 pts) ⬜
- [ ] **S7.2.1**: Create `src/oauth/token_storage.py` module
- [ ] **S7.2.2**: Implement `TokenData` dataclass with all fields
- [ ] **S7.2.3**: Add expiry calculation methods (`is_expired`, `expires_within`)
- [ ] **S7.2.4**: Implement `TokenStorage` class with file-based persistence
- [ ] **S7.2.5**: Use absolute path `/workspaces/options_income/.schwab_tokens.json`
- [ ] **S7.2.6**: Add JSON serialization/deserialization methods
- [ ] **S7.2.7**: Set secure file permissions (chmod 600) on token file
- [ ] **S7.2.8**: Verify write permissions work from both host and container
- [ ] **S7.2.9**: Handle corrupted/missing files gracefully
- [ ] **S7.2.10**: Create unit tests for storage operations (target: >95% coverage)

**Requirements**: FR-O8, FR-O9, FR-O10, FR-O18, NFR-O8 from oauth_requirements.md
**Dependencies**: S7.1 (config)
**Deliverable**: Secure file-based token persistence with container compatibility

#### S7.3: Token Manager Core (2 pts) ⬜
- [ ] **S7.3.1**: Create `src/oauth/token_manager.py` module
- [ ] **S7.3.2**: Implement `TokenManager` class initialization
- [ ] **S7.3.3**: Implement `exchange_code_for_tokens()` method
- [ ] **S7.3.4**: Implement `refresh_tokens()` method with retry logic
- [ ] **S7.3.5**: Implement `get_valid_access_token()` with auto-refresh
- [ ] **S7.3.6**: Add `is_authorized()` and `get_token_status()` methods
- [ ] **S7.3.7**: Implement `revoke()` for local token deletion
- [ ] **S7.3.8**: Add Basic Auth header generation for token requests
- [ ] **S7.3.9**: Create custom exceptions (TokenExchangeError, TokenRefreshError, etc.)

**Requirements**: FR-O7, FR-O11, FR-O12, FR-O13, FR-O15, NFR-O4 from oauth_requirements.md
**Dependencies**: S7.2 (token storage)
**Deliverable**: Complete token lifecycle management

#### S7.4: Error Handling & Logging (2 pts) ⬜
- [ ] **S7.4.1**: Create `src/oauth/exceptions.py` with error hierarchy
- [ ] **S7.4.2**: Implement `SchwabOAuthError` base class
- [ ] **S7.4.3**: Add specific exception classes (ConfigurationError, AuthorizationError, etc.)
- [ ] **S7.4.4**: Implement comprehensive logging throughout OAuth module
- [ ] **S7.4.5**: Add retry logic with exponential backoff for network errors
- [ ] **S7.4.6**: Ensure client_secret never appears in logs or errors
- [ ] **S7.4.7**: Add clear, actionable error messages with recovery guidance
- [ ] **S7.4.8**: Create unit tests for error scenarios

**Requirements**: FR-O14, NFR-O4, NFR-O5, NFR-O7, NFR-O11 from oauth_requirements.md
**Dependencies**: S7.1, S7.2, S7.3
**Deliverable**: Robust error handling with security-conscious logging

**Acceptance Criteria**:
- AC-O1: Configuration loads from environment variables
- AC-O7: Tokens load correctly from file
- AC-O8: Token expiry calculated correctly
- AC-O10: Refresh updates stored tokens
- AC-O11: get_access_token returns valid token
- AC-O12: Missing tokens raise clear exception

---

### Sprint 8: Phase 9.2 - OAuth Authorization Flow (Est. 10 story points) ⬜ PLANNED

**Goal**: Implement OAuth 2.0 Authorization Code flow with HTTPS callback server and browser integration. **Critical**: Authorization server must run on HOST machine (not in container) to access SSL certificates and port 8443.

#### S8.1: HTTPS Callback Server (3 pts) ⬜
- [ ] **S8.1.1**: Create `src/oauth/auth_server.py` module
- [ ] **S8.1.2**: Implement `OAuthCallbackServer` class using Flask
- [ ] **S8.1.3**: Configure SSL context with certificates from `/etc/letsencrypt`
- [ ] **S8.1.4**: Verify SSL certificate access works on HOST machine
- [ ] **S8.1.5**: Implement `/oauth/callback` route handler
- [ ] **S8.1.6**: Parse authorization code from callback URL
- [ ] **S8.1.7**: Handle OAuth error responses (error, error_description)
- [ ] **S8.1.8**: Serve user-friendly HTML success/failure pages
- [ ] **S8.1.9**: Implement `/oauth/status` endpoint for debugging
- [ ] **S8.1.10**: Add server start/stop methods with threading support
- [ ] **S8.1.11**: Ensure server binds to 0.0.0.0 (accessible from router)

**Requirements**: FR-O5, FR-O16, NFR-O1, NFR-O9 from oauth_requirements.md
**Dependencies**: S7.1 (config)
**Deliverable**: HTTPS callback server that runs on host and receives authorization codes

#### S8.2: Authorization URL Generation & Browser Flow (2 pts) ⬜
- [ ] **S8.2.1**: Implement `generate_authorization_url()` method
- [ ] **S8.2.2**: Add correct query parameters (client_id, redirect_uri, response_type)
- [ ] **S8.2.3**: Implement automatic browser opening with `webbrowser` module
- [ ] **S8.2.4**: Display authorization URL in console for manual copy
- [ ] **S8.2.5**: Add configurable timeout for callback waiting (default: 5 minutes)
- [ ] **S8.2.6**: Create `AuthorizationResult` dataclass for flow results
- [ ] **S8.2.7**: Handle timeout scenarios gracefully

**Requirements**: FR-O4, FR-O6 from oauth_requirements.md
**Dependencies**: S8.1 (callback server)
**Deliverable**: Browser-integrated authorization flow

#### S8.3: Complete Authorization Flow Orchestration (2 pts) ⬜
- [ ] **S8.3.1**: Implement `run_authorization_flow()` function
- [ ] **S8.3.2**: Coordinate server start, URL generation, and callback waiting
- [ ] **S8.3.3**: Exchange authorization code for tokens upon success
- [ ] **S8.3.4**: Save tokens immediately after exchange
- [ ] **S8.3.5**: Ensure server cleanup on success, failure, and timeout
- [ ] **S8.3.6**: Add comprehensive logging for flow progress
- [ ] **S8.3.7**: Return clear success/failure indication to caller

**Requirements**: FR-O7, US-O1 from oauth_requirements.md
**Dependencies**: S7.3 (token manager), S8.1 (callback server), S8.2 (URL generation)
**Deliverable**: End-to-end authorization flow

#### S8.4: OAuth Coordinator High-Level Interface (2 pts) ⬜
- [ ] **S8.4.1**: Create `src/oauth/coordinator.py` module
- [ ] **S8.4.2**: Implement `OAuthCoordinator` class as main interface
- [ ] **S8.4.3**: Add `ensure_authorized()` method with auto-flow triggering
- [ ] **S8.4.4**: Implement `get_access_token()` for API client usage
- [ ] **S8.4.5**: Add `get_authorization_header()` helper method
- [ ] **S8.4.6**: Implement `is_authorized()` status check
- [ ] **S8.4.7**: Add `get_status()` for diagnostics and troubleshooting
- [ ] **S8.4.8**: Implement `revoke()` for authorization cleanup

**Requirements**: FR-O12, FR-O13, US-O3 from oauth_requirements.md
**Dependencies**: S7.3 (token manager), S8.3 (auth flow)
**Deliverable**: Simple, high-level OAuth interface for application use

#### S8.5: Host Authorization Script & Container Utility (2 pts) ⬜
- [ ] **S8.5.1**: Create `scripts/authorize_schwab_host.py` for HOST execution
- [ ] **S8.5.2**: Add banner clearly indicating "RUN ON HOST MACHINE"
- [ ] **S8.5.3**: Verify SSL certificate access at `/etc/letsencrypt`
- [ ] **S8.5.4**: Write tokens to `/workspaces/options_income/.schwab_tokens.json`
- [ ] **S8.5.5**: Set file permissions (chmod 600) after writing
- [ ] **S8.5.6**: Create `scripts/check_schwab_auth.py` for CONTAINER usage
- [ ] **S8.5.7**: Check script displays token status from container
- [ ] **S8.5.8**: Add `--revoke` flag to host script for token cleanup
- [ ] **S8.5.9**: Test complete user journey: host auth → container usage
- [ ] **S8.5.10**: Verify token refresh works from container

**Requirements**: US-O1, US-O4, US-O5, FR-O16, FR-O17, NFR-O12 from oauth_requirements.md
**Dependencies**: S8.4 (coordinator)
**Deliverable**: Split execution scripts (host authorization, container status check)

#### S8.6: Container Architecture Setup (1 pt) ⬜
- [ ] **S8.6.1**: Add `.schwab_tokens.json` to `.gitignore`
- [ ] **S8.6.2**: Verify `.devcontainer/devcontainer.json` has SSL mount
- [ ] **S8.6.3**: Create `docs/CONTAINER_ARCHITECTURE.md` documentation
- [ ] **S8.6.4**: Document host vs container execution model
- [ ] **S8.6.5**: Add troubleshooting section for permission issues
- [ ] **S8.6.6**: Create workflow diagram for first-time setup
- [ ] **S8.6.7**: Document token file location and rationale
- [ ] **S8.6.8**: Add examples of host auth + container usage

**Requirements**: FR-O17, FR-O18, NFR-O15 from oauth_requirements.md
**Dependencies**: S8.5 (scripts)
**Deliverable**: Complete container architecture documentation and configuration

**Acceptance Criteria**:
- AC-O1: Callback server starts on configured port with HTTPS (on HOST)
- AC-O2: Authorization URL contains correct parameters
- AC-O3: Callback correctly extracts authorization code
- AC-O4: Token exchange returns valid tokens
- AC-O5: Tokens saved to project directory
- AC-O6: Error responses handled gracefully
- AC-O20: Authorization script runs successfully on host
- AC-O21: Token file written to `/workspaces/options_income/.schwab_tokens.json`
- AC-O25: .gitignore excludes token file

---

### Sprint 9: Phase 9.3 - Schwab API Client & Integration (Est. 9 story points) ⬜ PLANNED

**Goal**: Build Schwab API client with OAuth integration and connect to wheel strategy system.

#### S9.1: Schwab API Client Foundation (3 pts) ⬜
- [ ] **S9.1.1**: Create `src/schwab/` module directory
- [ ] **S9.1.2**: Create `src/schwab/client.py` with `SchwabClient` class
- [ ] **S9.1.3**: Integrate `OAuthCoordinator` for authentication
- [ ] **S9.1.4**: Implement `_request()` method with automatic token refresh
- [ ] **S9.1.5**: Handle 401 responses with clear re-authorization messages
- [ ] **S9.1.6**: Add request/response logging (excluding sensitive data)
- [ ] **S9.1.7**: Implement retry logic for transient errors
- [ ] **S9.1.8**: Create `SchwabAuthenticationError` exception

**Requirements**: Section 4.1 from oauth_design.md
**Dependencies**: Sprint 8 (OAuth coordinator)
**Deliverable**: Authenticated HTTP client for Schwab APIs

#### S9.2: Schwab Market Data Endpoints (2 pts) ⬜
- [ ] **S9.2.1**: Create `src/schwab/endpoints.py` for API endpoint definitions
- [ ] **S9.2.2**: Implement `get_quote()` method for real-time quotes
- [ ] **S9.2.3**: Implement `get_option_chain()` method
- [ ] **S9.2.4**: Parse Schwab options chain format to internal `OptionsChain` model
- [ ] **S9.2.5**: Add error handling for invalid symbols
- [ ] **S9.2.6**: Cache Schwab responses using existing cache infrastructure
- [ ] **S9.2.7**: Create unit tests with mocked Schwab responses

**Requirements**: Section 4.1 from oauth_design.md
**Dependencies**: S9.1 (client foundation)
**Deliverable**: Market data API methods

#### S9.3: Schwab Account Data Endpoints (2 pts) ⬜
- [ ] **S9.3.1**: Implement `get_accounts()` method
- [ ] **S9.3.2**: Implement `get_account_positions()` method
- [ ] **S9.3.3**: Create `src/schwab/models.py` for Schwab-specific data models
- [ ] **S9.3.4**: Define `SchwabAccount`, `SchwabPosition` dataclasses
- [ ] **S9.3.5**: Parse account/position data from Schwab format
- [ ] **S9.3.6**: Add integration with wheel strategy for position import
- [ ] **S9.3.7**: Create unit tests for account data parsing

**Requirements**: Section 2.1 from oauth_requirements.md (Business Context)
**Dependencies**: S9.1 (client foundation)
**Deliverable**: Account data retrieval methods

#### S9.4: Wheel Strategy Schwab Integration (2 pts) ⬜
- [ ] **S9.4.1**: Add Schwab client option to `WheelManager.__init__()`
- [ ] **S9.4.2**: Update `RecommendEngine` to support Schwab as data source
- [ ] **S9.4.3**: Add `--broker schwab` option to wheel CLI
- [ ] **S9.4.4**: Implement automatic position import from Schwab accounts
- [ ] **S9.4.5**: Add configuration option for preferred data source
- [ ] **S9.4.6**: Update CLI to show data source in status output
- [ ] **S9.4.7**: Add fallback to Finnhub if Schwab unavailable

**Requirements**: Integration requirements
**Dependencies**: S9.2, S9.3 (Schwab endpoints), existing wheel strategy
**Deliverable**: Schwab integration in wheel strategy tool

**Acceptance Criteria**:
- AC-O17: Authorization header format correct
- AC-O18: Schwab API call succeeds with token
- AC-O19: 401 response triggers appropriate error
- Wheel CLI can fetch data from Schwab
- Position import works from Schwab accounts

---

### Sprint 10: Phase 9.4 - Testing, Documentation & Deployment (Est. 8 story points) ⬜ PLANNED

**Goal**: Comprehensive testing, documentation, and production deployment of OAuth integration.

#### S10.1: Unit Tests (3 pts) ⬜
- [ ] **S10.1.1**: Create `tests/oauth/test_config.py` (target: 100% coverage)
- [ ] **S10.1.2**: Create `tests/oauth/test_token_storage.py` (target: 95% coverage)
- [ ] **S10.1.3**: Create `tests/oauth/test_token_manager.py` (target: 90% coverage)
- [ ] **S10.1.4**: Create `tests/oauth/test_auth_server.py` (target: 80% coverage)
- [ ] **S10.1.5**: Create `tests/oauth/test_coordinator.py` (target: 85% coverage)
- [ ] **S10.1.6**: Create `tests/schwab/test_client.py` (target: 85% coverage)
- [ ] **S10.1.7**: Mock all external API calls (Schwab OAuth, Schwab API)
- [ ] **S10.1.8**: Test all error paths and edge cases

**Requirements**: Section 10 from oauth_requirements.md, NFR-O14
**Dependencies**: Sprints 7, 8, 9 (all implementation)
**Deliverable**: >85% test coverage for OAuth module

#### S10.2: Integration Tests (2 pts) ⬜
- [ ] **S10.2.1**: Create mock Schwab OAuth server for integration testing
- [ ] **S10.2.2**: Test complete authorization flow end-to-end (host execution)
- [ ] **S10.2.3**: Test token refresh cycle simulation (container execution)
- [ ] **S10.2.4**: Test token file written by host, read by container
- [ ] **S10.2.5**: Test token file refresh from container, readable by host
- [ ] **S10.2.6**: Test error recovery scenarios (network failures, expired tokens)
- [ ] **S10.2.7**: Test OAuth + Schwab API integration from container
- [ ] **S10.2.8**: Test wheel strategy with Schwab data source
- [ ] **S10.2.9**: Validate against Schwab sandbox environment (if available)

**Requirements**: Section 10.3 from oauth_requirements.md, AC-O22, AC-O23
**Dependencies**: S10.1 (unit tests)
**Deliverable**: Integration test suite with container architecture validation

#### S10.3: Documentation (2 pts) ⬜
- [ ] **S10.3.1**: Create `docs/SCHWAB_OAUTH_SETUP.md` with detailed setup instructions
- [ ] **S10.3.2**: Document split execution model (host vs container)
- [ ] **S10.3.3**: Document Schwab Developer Portal app registration
- [ ] **S10.3.4**: Document SSL certificate setup (Let's Encrypt)
- [ ] **S10.3.5**: Document port forwarding configuration
- [ ] **S10.3.6**: Create container architecture troubleshooting section
- [ ] **S10.3.7**: Add workflow diagrams for host auth + container usage
- [ ] **S10.3.8**: Create troubleshooting guide for common OAuth errors
- [ ] **S10.3.9**: Update main README.md with Schwab integration section
- [ ] **S10.3.10**: Add code documentation (docstrings) to all OAuth modules
- [ ] **S10.3.11**: Create example usage scripts (host and container)

**Requirements**: Section 11 from oauth_requirements.md, NFR-O13, NFR-O15
**Dependencies**: Sprints 7, 8, 9, S8.6 (container docs)
**Deliverable**: Complete documentation package with container architecture guide

#### S10.4: Manual Testing & Production Deployment (1 pt) ⬜
- [ ] **S10.4.1**: Verify Schwab Dev Portal app configuration
- [ ] **S10.4.2**: Test Let's Encrypt certificate renewal process
- [ ] **S10.4.3**: Verify port forwarding (8443 → host machine)
- [ ] **S10.4.4**: Verify `.devcontainer/devcontainer.json` SSL mount
- [ ] **S10.4.5**: Test authorization flow ON HOST machine
- [ ] **S10.4.6**: Verify token file written to project directory
- [ ] **S10.4.7**: Test wheel CLI FROM CONTAINER reads tokens
- [ ] **S10.4.8**: Test token auto-refresh from container (wait 25 min or mock)
- [ ] **S10.4.9**: Verify refreshed tokens written back successfully
- [ ] **S10.4.10**: Test re-authorization after token expiry (host script)
- [ ] **S10.4.11**: Test .gitignore excludes token file
- [ ] **S10.4.12**: Run complete manual test checklist

**Requirements**: Section 8 from oauth_design.md (Deployment Checklist), AC-O20 through AC-O25
**Dependencies**: S10.3 (documentation)
**Deliverable**: Production-ready OAuth integration with container architecture validation

**Acceptance Criteria**:
- OAuth module >85% test coverage
- All manual test scenarios pass (host + container)
- Documentation complete and accurate with container architecture
- Wheel CLI successfully uses Schwab data from container
- Token refresh works automatically from container
- Re-authorization process is smooth (host execution)
- Token file location works in both contexts
- .gitignore properly configured

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
| `src/risk_analyzer.py` | 95% | 90% | ✅ Exceeds target |
| `src/earnings_calendar.py` | 98% | 90% | ✅ Exceeds target |
| **Overall** | 79% | **80%** | 446 tests passing |

### OAuth Module Coverage Goals (Phase 9)

| Module | Target | Status | Notes |
|--------|--------|--------|-------|
| `src/oauth/config.py` | 100% | ⬜ | Configuration management |
| `src/oauth/token_storage.py` | 95% | ⬜ | Token persistence |
| `src/oauth/token_manager.py` | 90% | ⬜ | Token lifecycle |
| `src/oauth/auth_server.py` | 80% | ⬜ | Flask callback server |
| `src/oauth/coordinator.py` | 85% | ⬜ | High-level interface |
| `src/oauth/exceptions.py` | 100% | ⬜ | Error classes |
| `src/schwab/client.py` | 85% | ⬜ | Schwab API client |
| `src/schwab/models.py` | 100% | ⬜ | Data models |
| **OAuth Overall** | **>85%** | ⬜ | Target for Phase 9 |

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

### OAuth Integration (AC-O1 to AC-O25)

| # | Criterion | Status |
|---|-----------|--------|
| AC-O1 | Callback server starts on configured port with HTTPS (HOST) | ⬜ |
| AC-O2 | Authorization URL contains correct parameters | ⬜ |
| AC-O3 | Callback correctly extracts authorization code | ⬜ |
| AC-O4 | Token exchange returns valid tokens | ⬜ |
| AC-O5 | Tokens saved to project directory | ⬜ |
| AC-O6 | Error responses handled gracefully | ⬜ |
| AC-O7 | Tokens load correctly from file (CONTAINER) | ⬜ |
| AC-O8 | Token expiry calculated correctly | ⬜ |
| AC-O9 | Auto-refresh triggers before expiry (CONTAINER) | ⬜ |
| AC-O10 | Refresh updates stored tokens (CONTAINER) | ⬜ |
| AC-O11 | get_access_token returns valid token | ⬜ |
| AC-O12 | Missing tokens raise clear exception | ⬜ |
| AC-O13 | Missing config raises ConfigurationError | ⬜ |
| AC-O14 | Network errors trigger retry | ⬜ |
| AC-O15 | Invalid refresh token raises clear error | ⬜ |
| AC-O16 | Corrupted token file handled | ⬜ |
| AC-O17 | Authorization header format correct | ⬜ |
| AC-O18 | Schwab API call succeeds with token | ⬜ |
| AC-O19 | 401 response triggers appropriate error | ⬜ |
| AC-O20 | Authorization script runs successfully on host | ⬜ |
| AC-O21 | Token file written to `/workspaces/options_income/.schwab_tokens.json` | ⬜ |
| AC-O22 | Application in container reads tokens successfully | ⬜ |
| AC-O23 | Token refresh from container writes back successfully | ⬜ |
| AC-O24 | Same absolute path works in both contexts | ⬜ |
| AC-O25 | .gitignore excludes token file | ⬜ |

---

## Dependencies & Blockers

| Item | Type | Status | Notes |
|------|------|--------|-------|
| Alpha Vantage API key | Dependency | ✅ | User has key |
| Finnhub API key | Dependency | ✅ | User has key |
| TIME_SERIES_DAILY_ADJUSTED response structure | Dependency | ✅ | Documented in PRD |
| Schwab Developer Portal App | Dependency | ⬜ | Must register app for OAuth credentials |
| Domain with SSL (dirtydata.ai) | Dependency | ⬜ | Required for HTTPS callback |
| Let's Encrypt SSL Certificate | Dependency | ⬜ | For callback server HTTPS |
| Port 8443 forwarding | Dependency | ⬜ | Router must forward to local machine |
| Schwab OAuth Sandbox Access | Optional | ⬜ | For integration testing (if available) |

---

## Notes

- All tests currently pass (446 tests)
- Basic end-to-end workflow functional (`example_end_to_end.py`)
- Sprint 2 complete: Strike Optimization module with 53 tests
- Sprint 3 complete: Covered Strategies module with 48 tests
- Sprint 4 complete: Overlay Scanner module with 70 tests
- Sprint 5 complete: Ladder Builder module with 40 tests (91% coverage)
- Sprint 6 complete: Risk Analyzer module with 31 tests (95% coverage), EarningsEvent dataclass with 23 tests
- Fixed critical IV conversion bug (Finnhub returns IV as percentage, not decimal)
- Cache system refactored to unified `market_data` table
- Performance validated: 300 core calculations in 68ms (< 500ms requirement)
- Each sprint deliverable should include updated unit tests

### OAuth Module Notes

- Phase 9 adds Schwab API integration via OAuth 2.0 Authorization Code flow
- **Container Architecture**: Split execution model required
  - Authorization (OAuth callback server) runs on **HOST** machine
  - Application (wheel strategy) runs in **DEVCONTAINER**
  - Token file stored in project directory (shared workspace)
  - Same absolute path works in both contexts: `/workspaces/options_income/.schwab_tokens.json`
- OAuth implementation follows security best practices:
  - Client secret in environment variables only
  - Token file restricted to user-only permissions (chmod 600)
  - Token file excluded from git (.gitignore)
  - No sensitive data in logs or error messages
  - HTTPS required for callback server
- Infrastructure prerequisites:
  - Domain with DNS (dirtydata.ai with dyndns)
  - Let's Encrypt SSL certificate (mounted in devcontainer)
  - Port forwarding configured (8443 → host machine)
  - Schwab Developer Portal app registered
  - Devcontainer with SSL mount configured
- Design documents:
  - `docs/oauth_design.md` - Technical architecture and specifications (updated for containers)
  - `docs/oauth_requirements.md` - Functional and non-functional requirements (updated for containers)
  - `docs/CONTAINER_ARCHITECTURE.md` - Container deployment guide (new)
- Estimated timeline: 4 sprints (37 story points total, +2 for container architecture)
- OAuth module will enable:
  - Live market data from Schwab
  - Automatic position import from brokerage accounts
  - Foundation for future order placement features
  - Higher quality data from primary source (broker)
- Key architectural decisions:
  - Option 1 (selected): Token file in project directory
  - Rationale: No additional mounts, same path everywhere, simple
  - Trade-off: Token file in project (but gitignored)

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
| 1.6 | 2026-01-20 | Software Developer | Sprint 6 complete: Risk Analyzer module implemented with 31 tests (95% coverage). Features: income metrics (annualized yield, returns, breakevens), risk metrics (expected value, opportunity cost, Sharpe-like ratio), scenario analysis engine, strategy comparison. EarningsEvent dataclass added with 23 tests (98% coverage). README.md created. All Sprint 6 acceptance criteria met. |
| 1.7 | 2026-01-25 | Software Developer | Added Phase 9: Schwab OAuth Integration. Analyzed oauth_design.md and oauth_requirements.md to create phased development plan across 4 sprints (35 story points). Sprints 7-10 cover: OAuth core infrastructure, authorization flow, Schwab API client integration, and comprehensive testing/documentation. Added OAuth-specific acceptance criteria (AC-O1 to AC-O19), infrastructure dependencies, and implementation notes. |
| 1.8 | 2026-01-25 | Software Developer | Updated Phase 9 for devcontainer architecture (Option 1: project directory). All three documents updated (oauth_design.md, oauth_requirements.md, IMPLEMENTATION_PLAN.md) to reflect split execution model: authorization runs on HOST (needs SSL certs, port 8443), application runs in CONTAINER. Token file at `/workspaces/options_income/.schwab_tokens.json` (same path everywhere). Added 6 new acceptance criteria (AC-O20 to AC-O25) for container architecture. Updated sprints 7-10 with container-specific tasks (+2 story points for S8.6). Added CONTAINER_ARCHITECTURE.md documentation task. |
