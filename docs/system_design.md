# System Design Document (SDD)
## Covered Options Strategy Optimization System

**Version:** 2.1
**Date:** January 18, 2026
**Status:** Draft (Updated for Weekly Overlay Scanner)

---

## 1. Overview

This document describes the architecture and module-level design for the Covered Options Strategy Optimization System. Version 2.1 adds a holdings-driven **weekly covered-call overlay scanner** that sizes trades using a configurable overwrite cap (default 25%), ranks opportunities on **net credit** after execution costs, and excludes earnings-week expirations by default.

## 2. Architecture Summary

### 2.1 High-Level Flow (Scanner Mode)

1. Load portfolio holdings (`symbol`, `shares`, optional tax context)
2. Fetch/compute market context (spot, vol, chain, events)
3. Generate candidate covered calls in target **delta bands** for next 1–3 weekly expirations (skipping earnings weeks)
4. Apply tradability filters and execution cost model to compute **net credit**
5. Rank candidates and output:
   - trade blotter (GO/CHECK/SKIP)
   - per-trade broker checklist
   - structured JSON payload for optional LLM decision memo

### 2.2 Key Design Principles

- **Broker-first execution**: the system scans and explains; the user executes at the broker.
- **Hard event gates**: skip earnings weeks by default.
- **Net economics**: rank by net credit after fees/slippage, not raw premium.
- **Explainability**: emit rejection reasons for filtered strikes and surface data-quality warnings.

## 3. Core Modules

### 3.1 Configuration (`config.py`)

Configuration extends existing API keys and caching settings with scanner settings:

- `overwrite_cap_pct` (default 25.0)
- `per_contract_fee` (tunable)
- `slippage_model` (default `half_spread_capped`)
- `skip_earnings_default` (default true)
- delta-band presets (defensive/conservative/moderate/aggressive)

### 3.2 Data Models (`models.py`)

Additions for scanner mode:

- `Holding(symbol, shares, cost_basis?, acquired_date?, account_type?)`
- `ExecutionCostModel(per_contract_fee, slippage_model, min_net_credit)`
- `EventRiskFlags(earnings_in_window, ex_div_in_window, dividend_unverified, early_exercise_risk)`
- `TradabilityScore(spread_abs, spread_pct_mid, oi, volume, quote_age?, is_tradeable, reasons[])`
- `TradeCandidate` (contract + computed metrics + sizing + warnings)
- `TradeChecklistItem` and `TradeDecisionMemoPayload`

### 3.3 Local File Cache (`cache.py`)

The cache supports price and earnings calendar caching plus Alpha Vantage daily usage tracking.

```python
# (excerpt; leading lines omitted for brevity)
with open(cache_path, "r") as f:
                data = json.load(f)
            
            # Check expiry
            if max_age_hours is not None:
                cached_at = datetime.fromisoformat(data.get("_cached_at", "1970-01-01"))
                age_hours = (datetime.now() - cached_at).total_seconds() / 3600
                if age_hours > max_age_hours:
                    logging.debug(f"Cache expired: {key} (age: {age_hours:.1f}h)")
                    return None
            
            logging.debug(f"Cache hit: {key}")
            return data
            
        except (json.JSONDecodeError, KeyError) as e:
            logging.warning(f"Cache read error for {key}: {e}")
            return None
    
    def set(self, key: str, data: Dict[str, Any]) -> None:
        """
        Store data in cache.
        
        Args:
            key: Cache key
            data: Data to cache (must be JSON serializable)
        """
        cache_path = self._get_cache_path(key)
        data["_cached_at"] = datetime.now().isoformat()
        
        try:
            with open(cache_path, "w") as f:
                json.dump(data, f, indent=2)
            logging.debug(f"Cached: {key}")
        except IOError as e:
            logging.error(f"Cache write error for {key}: {e}")
    
    def delete(self, key: str) -> bool:
        """Delete a cache entry."""
        cache_path = self._get_cache_path(key)
        if cache_path.exists():
            cache_path.unlink()
            return True
        return False
    
    def clear_all(self) -> int:
        """Clear all cache entries. Returns count of deleted files."""
        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            if cache_file.name != "api_usage.json":
                cache_file.unlink()
                count += 1
        return count
    
    # ==================== API Usage Tracking ====================
    
    def get_alpha_vantage_usage_today(self) -> int:
        """Get number of Alpha Vantage API calls made today."""
        usage = self._load_usage()
        today = datetime.now().strftime("%Y-%m-%d")
        return usage.get("alpha_vantage", {}).get(today, 0)
    
    def increment_alpha_vantage_usage(self) -> int:
        """Increment and return today's Alpha Vantage usage count."""
        usage = self._load_usage()
        today = datetime.now().strftime("%Y-%m-%d")
        
        if "alpha_vantage" not in usage:
            usage["alpha_vantage"] = {}
        
        usage["alpha_vantage"][today] = usage["alpha_vantage"].get(today, 0) + 1
        self._save_usage(usage)
        
        return usage["alpha_vantage"][today]
    
    def _load_usage(self) -> Dict[str, Any]:
        """Load API usage tracking data."""
        if self._usage_file.exists():
            try:
                with open(self._usage_file, with open(cache_path, "r") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return {}
        return {}
    
    def _save_usage(self, usage: Dict[str, Any]) -> None:
        """Save API usage tracking data."""
        with open(self._usage_file, "w") as f:
            json.dump(usage, f, indent=2)
```

**Design Decisions**:
- File-based cache for simplicity (no external dependencies like Redis)
- JSON format for human readability and debugging
- Automatic TTL checking on read
- Separate API usage tracking for Alpha Vantage daily limits
- Safe key sanitization for filesystem compatibility

---

### 3.4 Alpha Vantage Client Module (`alphavantage_client.py`)

**Purpose**: Handle all HTTP communication with Alpha Vantage API with efficient data retrieval.

**Responsibilities**:
- Fetch historical OHLC data with dividends and splits
- Maximize data per API call (critical for 25/day limit)
- Track and enforce daily usage limits
- Parse API responses into data models

**Key Components**:

```python
class AlphaVantageClient:
    """Client for Alpha Vantage API with efficient data retrieval."""
    
    def __init__(self, config: AlphaVantageConfig, cache: LocalFileCache):
        self.config = config
        self.cache = cache
        self.session = requests.Session()
    
    def get_daily_adjusted(
        self,
        symbol: str,
        outputsize: str = "compact"  # "compact" = 100 days, "full" = 20+ years
    ) -> PriceHistory:
        """
        Fetch daily OHLC data with dividends and splits.
        
        This is the most efficient call - gets OHLC, dividends, and splits
        in a single API request.
        
        Args:
            symbol: Stock ticker symbol
            outputsize: "compact" for 100 days, "full" for complete history
            
        Returns:
            PriceHistory with all price bars
        """
        # Check cache first
        cache_key = f"price_daily_{symbol}_{outputsize}"
        cached = self.cache.get(cache_key, max_age_hours=self.config.price_data_ttl_hours)
        if cached:
            return self._parse_cached_price_history(cached, symbol)
        
        # Check daily limit
        usage = self.cache.get_alpha_vantage_usage_today()
        if usage >= self.config.daily_limit:
            raise AlphaVantageRateLimitError(
                f"Alpha Vantage daily limit reached ({usage}/{self.config.daily_limit}). "
                "Resets at midnight. Consider using cached data or upgrading plan."
            )
        
        # Make API call (using TIME_SERIES_DAILY for free tier)
        # Note: TIME_SERIES_DAILY_ADJUSTED requires premium subscription
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "outputsize": outputsize,
            "apikey": self.config.api_key
        }
        
        response = self.session.get(
            self.config.base_url,
            params=params,
            timeout=self.config.timeout
        )
        response.raise_for_status()
        data = response.json()
        
        # Check for API errors
        if "Error Message" in data:
            raise AlphaVantageAPIError(data["Error Message"])
        if "Note" in data:  # Rate limit warning
            raise AlphaVantageRateLimitError(data["Note"])
        
        # Increment usage counter
        self.cache.increment_alpha_vantage_usage()
        
        # Parse response
        price_history = self._parse_daily_response(data, symbol)
        
        # Cache the raw response
        self.cache.set(cache_key, data)
        
        return price_history
    
    def _parse_daily_response(
        self,
        data: Dict[str, Any],
        symbol: str
    ) -> PriceHistory:
        """Parse TIME_SERIES_DAILY response into PriceHistory."""
        time_series = data.get("Time Series (Daily)", {})

        bars = []
        for date_str, values in time_series.items():
            bar = PriceBar(
                date=date_str,
                open=float(values["1. open"]),
                high=float(values["2. high"]),
                low=float(values["3. low"]),
                close=float(values["4. close"]),
                volume=int(values["5. volume"]),
                # Note: adjusted_close, dividend, split_coefficient
                # require premium TIME_SERIES_DAILY_ADJUSTED
                adjusted_close=None,
                dividend=None,
                split_coefficient=None
            )
            bars.append(bar)

        return PriceHistory(
            symbol=symbol,
            bars=bars,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            source="alpha_vantage"
        )
    
    def get_usage_status(self) -> Dict[str, Any]:
        """Get current API usage status."""
        usage = self.cache.get_alpha_vantage_usage_today()
        return {
            "calls_today": usage,
            "daily_limit": self.config.daily_limit,
            "remaining": self.config.daily_limit - usage,
            "percentage_used": (usage / self.config.daily_limit) * 100
        }
    
    def close(self):
        """Close the HTTP session."""
        self.session.close()


class AlphaVantageAPIError(Exception):
    """Alpha Vantage API error."""
    pass


class AlphaVantageRateLimitError(AlphaVantageAPIError):
    """Alpha Vantage rate limit exceeded."""
    pass
```

**Design Decisions**:
- Use `TIME_SERIES_DAILY` for free tier (OHLC + volume)
- `TIME_SERIES_DAILY_ADJUSTED` (dividends/splits) requires premium subscription
- Cache-first pattern to minimize API calls (24-hour TTL)
- Track daily usage with clear warnings
- Clear separation of rate limit errors from other API errors
- Known limitation: Stock splits within 100-day window may affect volatility accuracy

---

### 3.5 Finnhub Client Module (`finnhub_client.py`)

**Purpose**: Handle HTTP communication with Finnhub API.

**Responsibilities**:
- Fetch options chain data
- Fetch current stock quote
- Fetch earnings calendar
- Handle rate limiting and retries

**Key Components**:

```python
class FinnhubClient:
    """Client for Finnhub API."""

    def __init__(self, config: FinnhubConfig, cache: Optional[LocalFileCache] = None):
        self.config = config
        self.cache = cache
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "CoveredOptionsSystem/2.0"
        })

    def get_option_chain(self, symbol: str) -> Dict[str, Any]:
        """Retrieve options chain for a symbol."""
        symbol = symbol.upper().strip()
        if not symbol or not symbol.isalpha():
            raise ValueError(f"Invalid symbol: {symbol}")

        url = f"{self.config.base_url}/stock/option-chain"
        params = {
            "symbol": symbol,
            "token": self.config.api_key
        }

        response = self._make_request_with_retry(url, params)
        return response.json()

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get current stock quote."""
        url = f"{self.config.base_url}/quote"
        params = {
            "symbol": symbol.upper(),
            "token": self.config.api_key
        }
        
        response = self._make_request_with_retry(url, params)
        return response.json()

    def get_earnings_calendar(
        self,
        symbol: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> List[EarningsEvent]:
        """
        Get earnings calendar.
        
        Args:
            symbol: Filter by symbol (optional)
            from_date: Start date YYYY-MM-DD
            to_date: End date YYYY-MM-DD
        """
        # Check cache for earnings (weekly refresh)
        if self.cache and symbol:
            cache_key = f"earnings_{symbol}"
            cached = self.cache.get(cache_key, max_age_hours=168)  # 7 days
            if cached:
                return self._parse_earnings_from_cache(cached)
        
        url = f"{self.config.base_url}/calendar/earnings"
        params = {"token": self.config.api_key}
        
        if symbol:
            params["symbol"] = symbol.upper()
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        
        response = self._make_request_with_retry(url, params)
        data = response.json()
        
        # Cache if symbol-specific
        if self.cache and symbol:
            self.cache.set(cache_key, data)
        
        return self._parse_earnings_response(data)

    def _make_request_with_retry(
        self,
        url: str,
        params: Dict[str, str],
        attempt: int = 1
    ) -> requests.Response:
        """Make HTTP request with exponential backoff retry."""
        try:
            response = self.session.get(
                url, params=params, timeout=self.config.timeout
            )
            
            # Handle specific HTTP errors
            if response.status_code == 401:
                raise FinnhubAPIError("Invalid API key")
            elif response.status_code == 429:
                raise FinnhubRateLimitError("Rate limit exceeded")
            elif response.status_code >= 500:
                raise FinnhubAPIError(f"Server error: {response.status_code}")
            
            response.raise_for_status()
            return response
            
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            if attempt >= self.config.max_retries:
                raise FinnhubAPIError(f"Request failed after {attempt} attempts: {e}")
            
            delay = self.config.retry_delay * (2 ** (attempt - 1))
            logging.warning(f"Request failed (attempt {attempt}), retrying in {delay}s...")
            time.sleep(delay)
            return self._make_request_with_retry(url, params, attempt + 1)

    def close(self):
        """Close HTTP session."""
        self.session.close()


class FinnhubAPIError(Exception):
    """Finnhub API error."""
    pass


class FinnhubRateLimitError(FinnhubAPIError):
    """Finnhub rate limit exceeded."""
    pass
```

---

### 3.6 Volatility Module (`volatility.py`)

**Purpose**: Calculate various volatility measures from price data.

**Note**: This module is already implemented (Phase 2 complete). Key components include:

```python
class VolatilityCalculator:
    """Calculate various volatility measures from price data."""
    
    def calculate_close_to_close(
        self, prices: List[float], window: int = 20, annualize: bool = True
    ) -> VolatilityResult:
        """Calculate close-to-close realized volatility."""
        
    def calculate_parkinson(
        self, highs: List[float], lows: List[float], window: int = 20
    ) -> VolatilityResult:
        """Calculate Parkinson (high-low) volatility."""
        
    def calculate_garman_klass(
        self, opens: List[float], highs: List[float], 
        lows: List[float], closes: List[float], window: int = 20
    ) -> VolatilityResult:
        """Calculate Garman-Klass volatility."""
        
    def calculate_yang_zhang(
        self, opens: List[float], highs: List[float],
        lows: List[float], closes: List[float], window: int = 20
    ) -> VolatilityResult:
        """Calculate Yang-Zhang volatility."""
        
    def calculate_blended(
        self, price_history: PriceHistory, implied_volatility: Optional[float],
        weights: Optional[BlendWeights] = None
    ) -> BlendedVolatility:
        """Calculate blended volatility estimate."""
```

---

### 3.7 Strike Optimizer Module (`strike_optimizer.py`)

**Purpose**: Calculate optimal strike prices for covered options.

**Key Components**:

```python
class StrikeOptimizer:
    """Calculate optimal strike prices for covered calls and puts."""
    
    def __init__(self, config: Optional[StrikeConfig] = None):
        self.config = config or StrikeConfig()
    
    def calculate_strike_at_sigma(
        self,
        current_price: float,
        volatility: float,
        sigma_distance: float,
        days_to_expiry: int,
        option_type: str = "call"
    ) -> StrikeResult:
        """
        Calculate strike price at N standard deviations.
        
        For calls: positive sigma_distance (strike above current price)
        For puts: negative sigma_distance (strike below current price)
        """
        T = days_to_expiry / 365.0
        
        # For puts, sigma_distance should be negative
        if option_type.lower() == "put" and sigma_distance > 0:
            sigma_distance = -sigma_distance
        
        theoretical_strike = current_price * math.exp(sigma_distance * volatility * math.sqrt(T))
        
        return StrikeResult(
            theoretical_strike=theoretical_strike,
            tradeable_strike=theoretical_strike,  # Will be rounded later
            sigma_distance=sigma_distance,
            current_price=current_price,
            volatility=volatility,
            days_to_expiry=days_to_expiry
        )
    
    def round_to_tradeable_strike(
        self,
        theoretical_strike: float,
        available_strikes: List[float],
        option_type: str = "call",
        conservative: bool = True
    ) -> float:
        """
        Round to nearest tradeable strike.
        
        If conservative:
        - Calls: round UP (further OTM)
        - Puts: round DOWN (further OTM)
        """
        if not available_strikes:
            # Round to common increments
            if theoretical_strike < 5:
                return round(theoretical_strike * 2) / 2  # $0.50 increments
            elif theoretical_strike < 25:
                return round(theoretical_strike)  # $1.00 increments
            else:
                return round(theoretical_strike / 2.5) * 2.5  # $2.50 increments
        
        # Find closest available strike
        if conservative:
            if option_type.lower() == "call":
                # Round up for calls
                candidates = [s for s in available_strikes if s >= theoretical_strike]
                return min(candidates) if candidates else max(available_strikes)
            else:
                # Round down for puts
                candidates = [s for s in available_strikes if s <= theoretical_strike]
                return max(candidates) if candidates else min(available_strikes)
        else:
            return min(available_strikes, key=lambda s: abs(s - theoretical_strike))
    
    def calculate_assignment_probability(
        self,
        current_price: float,
        strike: float,
        volatility: float,
        days_to_expiry: int,
        risk_free_rate: float = 0.05,
        option_type: str = "call"
    ) -> ProbabilityResult:
        """
        Calculate probability of assignment at expiration.
        
        For calls: P(S_T > K) = N(-d2)
        For puts: P(S_T < K) = N(d2)
        """
        T = days_to_expiry / 365.0
        
        d1 = (math.log(current_price / strike) + (risk_free_rate + 0.5 * volatility**2) * T) / (volatility * math.sqrt(T))
        d2 = d1 - volatility * math.sqrt(T)
        
        if option_type.lower() == "call":
            prob_itm = self._norm_cdf(-d2)
            delta = self._norm_cdf(d1)
        else:
            prob_itm = self._norm_cdf(d2)
            delta = -self._norm_cdf(-d1)
        
        return ProbabilityResult(
            probability_itm=prob_itm,
            delta=delta,
            d1=d1,
            d2=d2
        )
    
    def get_strike_recommendations(
        self,
        current_price: float,
        volatility: float,
        days_to_expiry: int,
        options_chain: OptionsChain,
        option_type: str = "call",
        profile: StrikeProfile = StrikeProfile.MODERATE,
        min_open_interest: int = 100,
        max_bid_ask_spread_pct: float = 0.10
    ) -> List[StrikeRecommendation]:
        """Get ranked strike recommendations with full metrics."""
        # Implementation continues...
    
    @staticmethod
    def _norm_cdf(x: float) -> float:
        """Standard normal cumulative distribution function."""
        return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0
```

---

### 3.8 Ladder Builder Module (`ladder_builder.py`)

**Purpose**: Build laddered covered option positions across multiple expirations.

**Key Components**:

```python
class LadderBuilder:
    """Build laddered covered call/put positions across expirations."""
    
    def __init__(
        self,
        volatility_calculator: VolatilityCalculator,
        strike_optimizer: StrikeOptimizer
    ):
        self.vol_calc = volatility_calculator
        self.strike_opt = strike_optimizer
    
    def build_ladder(
        self,
        symbol: str,
        total_shares: int,  # For calls: shares owned. For puts: cash / strike
        current_price: float,
        volatility: float,
        options_chain: OptionsChain,
        option_type: str = "call",
        num_weeks: int = 3,
        profile: StrikeProfile = StrikeProfile.MODERATE,
        allocation_strategy: AllocationStrategy = AllocationStrategy.EQUAL,
        exclude_earnings: bool = True,
        earnings_dates: Optional[List[str]] = None
    ) -> LadderResult:
        """Build complete ladder specification."""
        
        # Get weekly expirations
        expirations = self.get_weekly_expirations(
            options_chain, num_weeks, 
            exclude_dates=earnings_dates if exclude_earnings else None
        )
        
        # Calculate allocation per week
        allocations = self._calculate_allocations(
            total_shares, len(expirations), allocation_strategy
        )
        
        # Build each leg
        legs = []
        warnings = []
        
        for i, (expiration, shares) in enumerate(zip(expirations, allocations)):
            days_to_expiry = self._days_until(expiration)
            
            # Adjust sigma based on week
            base_sigma = self._get_sigma_for_profile(profile)
            adjusted_sigma = self._adjust_sigma_for_week(base_sigma, i, num_weeks)
            
            # Calculate strike
            strike_result = self.strike_opt.calculate_strike_at_sigma(
                current_price, volatility, adjusted_sigma, days_to_expiry, option_type
            )
            
            # Get contracts for this expiration
            exp_contracts = options_chain.get_by_expiration(expiration)
            contracts = [c for c in exp_contracts 
                        if (c.is_call if option_type == "call" else c.is_put)]
            
            available_strikes = [c.strike for c in contracts]
            tradeable_strike = self.strike_opt.round_to_tradeable_strike(
                strike_result.theoretical_strike, available_strikes, option_type
            )
            
            # Find the contract
            contract = next((c for c in contracts if c.strike == tradeable_strike), None)
            
            if contract and contract.bid:
                num_contracts = shares // 100
                leg = LadderLeg(
                    expiration_date=expiration,
                    days_to_expiry=days_to_expiry,
                    strike=tradeable_strike,
                    option_type=option_type.capitalize(),
                    sigma_distance=adjusted_sigma,
                    num_contracts=num_contracts,
                    num_shares=num_contracts * 100,
                    bid=contract.bid,
                    expected_premium=contract.bid * num_contracts * 100,
                    probability_itm=self.strike_opt.calculate_assignment_probability(
                        current_price, tradeable_strike, volatility, 
                        days_to_expiry, option_type=option_type
                    ).probability_itm,
                    annualized_yield=(contract.bid / current_price) * (365 / days_to_expiry)
                )
                legs.append(leg)
            else:
                warnings.append(f"No valid contract found for {expiration}")
        
        # Calculate aggregate metrics
        total_premium = sum(leg.expected_premium for leg in legs)
        total_contracts = sum(leg.num_contracts for leg in legs)
        
        return LadderResult(
            symbol=symbol,
            current_price=current_price,
            volatility_used=volatility,
            total_shares=total_shares,
            total_contracts=total_contracts,
            option_type=option_type.capitalize(),
            legs=legs,
            total_expected_premium=total_premium,
            weighted_avg_sigma=sum(l.sigma_distance * l.num_contracts for l in legs) / total_contracts if total_contracts else 0,
            weighted_avg_prob_itm=sum(l.probability_itm * l.num_contracts for l in legs) / total_contracts if total_contracts else 0,
            weighted_avg_yield=sum(l.annualized_yield * l.num_contracts for l in legs) / total_contracts if total_contracts else 0,
            generated_at=datetime.now(timezone.utc).isoformat(),
            warnings=warnings
        )
    
    def get_weekly_expirations(
        self,
        options_chain: OptionsChain,
        num_weeks: int,
        exclude_dates: Optional[List[str]] = None
    ) -> List[str]:
        """Get next N weekly expiration dates, excluding specified dates."""
        all_expirations = options_chain.get_expirations()
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Filter to future dates
        future_exps = [e for e in all_expirations if e > today]
        
        # Exclude specified dates (earnings weeks)
        if exclude_dates:
            future_exps = [e for e in future_exps 
                         if not any(self._dates_in_same_week(e, ed) for ed in exclude_dates)]
        
        return future_exps[:num_weeks]
```

---


### 3.9 Portfolio Overlay Scanner (`overlay_scanner.py`)

**Purpose**: Generate weekly covered-call recommendations for existing holdings with controlled assignment risk.

**Responsibilities**:
- Load holdings list and compute contract sizing from overwrite cap
- Enumerate next 1–3 weekly expirations; **exclude earnings weeks by default**
- Select candidate calls using delta bands as primary risk control
- Apply tradability filters (zero-bid removal, OI/volume/spread thresholds)
- Apply execution cost model (fees + slippage) to compute net credit
- Rank candidates and attach explicit rejection reasons for non-selected strikes

**Ranking objective (default)**:
- Maximize `net_premium_yield` subject to:
  - delta within profile band
  - event gates satisfied
  - tradability thresholds satisfied

### 3.10 Policy Engine (`policy_engine.py`)

**Purpose**: Encapsulate default management rules and allow user overrides.

**Default policy (configurable)**:
- take-profit target (e.g., 70–90% of premium)
- roll trigger: delta threshold and/or spot proximity to strike
- do-not-trade rules: earnings weeks (default), optional dividend risk tightening

### 3.11 Execution Checklist Generator (`execution_checklist.py`)

**Purpose**: Produce broker-side validation steps per recommended trade.

Checklist categories:
- Liquidity/pricing verification (broker quote vs scanner; limit order guidance)
- Event verification (earnings gate; ex-div confirmation; early exercise warning)
- Costs (fees/slippage; net credit confirmation)
- Position fit (contracts, overwrite cap, covered status)
- Management plan reminders (TP/roll triggers)

### 3.12 LLM Decision Memo Payload (`llm_memo.py`)

**Purpose**: Emit a structured JSON payload that an LLM can summarize into a concise decision memo.

**Design**:
- The system generates deterministic JSON (inputs, computed metrics, warnings).
- The LLM produces a narrative memo (rationale, risks, broker checks).
- This step is optional and must not change trade math.

### 3.13 Probability Conventions (`probability.py`)

**Requirement**: Define probability semantics explicitly and enforce with unit tests.

- Output `p_itm_model` (finish ITM probability) and `delta_chain` (market-implied proxy)
- Ensure monotonicity and sign conventions are tested to prevent accidental inversion

## 4. Error Handling Strategy

### 4.1 Error Hierarchy

```python
class CoveredOptionsError(Exception):
    """Base exception for covered options system."""
    pass

class ConfigurationError(CoveredOptionsError):
    """Configuration errors (missing API keys, invalid settings)."""
    pass

class APIError(CoveredOptionsError):
    """Base class for API errors."""
    pass

class FinnhubAPIError(APIError):
    """Finnhub API errors."""
    pass

class FinnhubRateLimitError(FinnhubAPIError):
    """Finnhub rate limit exceeded."""
    pass

class AlphaVantageAPIError(APIError):
    """Alpha Vantage API errors."""
    pass

class AlphaVantageRateLimitError(AlphaVantageAPIError):
    """Alpha Vantage daily limit exceeded."""
    pass

class DataValidationError(CoveredOptionsError):
    """Data validation errors."""
    pass

class CacheError(CoveredOptionsError):
    """Cache read/write errors."""
    pass
```

### 4.2 Error Handling Patterns

- **Configuration Errors**: Fail fast with clear messages
- **API Errors**: Retry transient errors, fail gracefully for permanent errors
- **Rate Limits**: Clear messaging, suggest alternatives (cache, wait, upgrade)
- **Data Validation**: Log warnings for non-critical issues, fail for critical
- **Cache Errors**: Fall through to API calls, log warning

---

## 5. Testing Strategy

### 5.1 Test Structure

```
tests/
├── test_config.py              # Configuration tests
├── test_models.py              # Data model tests
├── test_cache.py               # Cache tests
├── test_finnhub_client.py      # Finnhub client tests
├── test_alphavantage_client.py # Alpha Vantage client tests
├── test_volatility.py          # Volatility calculation tests
├── test_strike_optimizer.py    # Strike optimizer tests
├── test_ladder_builder.py      # Ladder builder tests
├── test_options_service.py     # Service layer tests
└── test_integration.py         # End-to-end integration tests
```

### 5.2 Coverage Goals

| Module | Target Coverage |
|--------|-----------------|
| config.py | 100% |
| models.py | 100% |
| cache.py | 95% |
| finnhub_client.py | 95% |
| alphavantage_client.py | 95% |
| volatility.py | 95% |
| strike_optimizer.py | 90% |
| ladder_builder.py | 90% |
| options_service.py | 90% |
| **Overall** | **>90%** |

---

## 6. Deployment

### 6.1 Dependencies

**`requirements.txt`**:
```
requests>=2.31.0
python-dotenv>=1.0.0
```

**`requirements-dev.txt`**:
```
pytest>=7.4.0
pytest-cov>=4.1.0
pytest-mock>=3.11.1
ruff>=0.4.0
mypy>=1.5.0
types-requests>=2.31.0
```

### 6.2 Configuration

```bash
# Required environment variables
export FINNHUB_API_KEY="your_finnhub_key"
export ALPHA_VANTAGE_API_KEY="your_alpha_vantage_key"

# Optional
export OPTIONS_CACHE_DIR="~/.options_cache"
```

---

## 7. Security Considerations

- API keys in environment variables only (never in code)
- Cache files stored in user's home directory with appropriate permissions
- Input validation on all ticker symbols
- No sensitive data in logs

---

## 8. Future Enhancements

### 8.1 Near-term
- Database integration for historical data storage
- Web API wrapper (FastAPI)
- Additional volatility estimators

### 8.2 Long-term
- Real-time WebSocket data
- ML/AI enhancements (see PRD Section 9.1)
- Web dashboard (React + TypeScript)

---

## 9. Appendix

### A. API Response Examples

See PRD Section 5.2 for detailed API response structures.

### B. Cache File Format

```json
{
  "_cached_at": "2026-01-15T10:30:00",
  "Meta Data": { ... },
  "Time Series (Daily)": { ... }
}
```

### C. Class Diagram

```
┌─────────────────────────┐
│      AppConfig          │
├─────────────────────────┤
│ + finnhub: FinnhubConfig│
│ + alpha_vantage: AVConfig│
│ + cache: CacheConfig    │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│   LocalFileCache        │
├─────────────────────────┤
│ + get()                 │
│ + set()                 │
│ + get_av_usage_today()  │
└───────────┬─────────────┘
            │
    ┌───────┴───────┐
    ▼               ▼
┌────────────┐  ┌────────────────┐
│FinnhubClient│  │AlphaVantageClient│
└─────┬──────┘  └───────┬────────┘
      │                 │
      └────────┬────────┘
               ▼
┌─────────────────────────┐
│  VolatilityCalculator   │
└───────────┬─────────────┘
            ▼
┌─────────────────────────┐
│   StrikeOptimizer       │
└───────────┬─────────────┘
            ▼
┌─────────────────────────┐
│    LadderBuilder        │
└─────────────────────────┘
```

---

**Document History**

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-13 | Software Developer | Initial design for Finnhub options chain |
| 2.0 | 2026-01-15 | Software Developer | Added Alpha Vantage integration, caching layer, covered puts, ladder builder |

---

**Document Approval**

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Tech Lead | | | |
| Senior Developer | | | |
| QA Lead | | | |
