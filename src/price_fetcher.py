"""
Historical price data fetcher for volatility calculations.

This module provides two data source options:

1. **Finnhub API** (Premium Required)
   - Uses /stock/candle endpoint
   - IMPORTANT: Requires paid Finnhub subscription
   - Free tier will return 403 Forbidden error

2. **Alpha Vantage API** (Free tier available)
   - Uses TIME_SERIES_DAILY endpoint (free tier)
   - Returns OHLC data with volume
   - Free tier limits: 25 requests/day, max 100 data points per request
   - Note: Adjusted close, dividends, and splits require premium (TIME_SERIES_DAILY_ADJUSTED)
   - API docs: https://www.alphavantage.co/documentation/
   - Get API key: https://www.alphavantage.co/support/#api-key

Usage:
    # Option 1: Finnhub (requires premium API key)
    from src.price_fetcher import PriceDataFetcher
    fetcher = PriceDataFetcher(finnhub_client)

    # Option 2: Alpha Vantage (free tier, recommended)
    from src.config import AlphaVantageConfig
    from src.cache import LocalFileCache
    from src.price_fetcher import AlphaVantagePriceDataFetcher

    config = AlphaVantageConfig.from_file()
    file_cache = LocalFileCache()  # Optional: for persistent caching
    fetcher = AlphaVantagePriceDataFetcher(config, file_cache=file_cache)
    price_data = fetcher.fetch_price_data("AAPL", lookback_days=60)

    # Note: dividend and split data requires premium API (TIME_SERIES_DAILY_ADJUSTED)
    # With free tier (TIME_SERIES_DAILY), these will be None
    print(price_data.dividends)          # None (requires premium)
    print(price_data.split_coefficients) # None (requires premium)

Both fetchers return PriceData objects compatible with the volatility calculator.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from dataclasses import dataclass

import requests

from .finnhub_client import FinnhubClient, FinnhubAPIError
from .volatility import PriceData

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cache entry for price data."""
    data: PriceData
    timestamp: float
    symbol: str
    lookback_days: int

    def is_valid(self, max_age_seconds: int = 3600) -> bool:
        """Check if cache entry is still valid."""
        age = time.time() - self.timestamp
        return age < max_age_seconds


class PriceDataCache:
    """Simple in-memory cache for price data."""

    def __init__(self, max_age_seconds: int = 3600):
        """
        Initialize cache.

        Args:
            max_age_seconds: Maximum age of cached data in seconds (default: 1 hour)
        """
        self._cache: Dict[str, CacheEntry] = {}
        self.max_age_seconds = max_age_seconds
        logger.debug(f"PriceDataCache initialized with max_age={max_age_seconds}s")

    def get(self, symbol: str, lookback_days: int) -> Optional[PriceData]:
        """
        Get cached price data if available and valid.

        Args:
            symbol: Stock ticker symbol
            lookback_days: Number of days of data requested

        Returns:
            PriceData if valid cache exists, None otherwise
        """
        cache_key = f"{symbol}:{lookback_days}"
        entry = self._cache.get(cache_key)

        if entry and entry.is_valid(self.max_age_seconds):
            logger.debug(f"Cache HIT for {cache_key}")
            return entry.data

        logger.debug(f"Cache MISS for {cache_key}")
        return None

    def set(self, symbol: str, lookback_days: int, data: PriceData) -> None:
        """
        Store price data in cache.

        Args:
            symbol: Stock ticker symbol
            lookback_days: Number of days of data
            data: PriceData to cache
        """
        cache_key = f"{symbol}:{lookback_days}"
        self._cache[cache_key] = CacheEntry(
            data=data,
            timestamp=time.time(),
            symbol=symbol,
            lookback_days=lookback_days
        )
        logger.debug(f"Cached price data for {cache_key}")

    def clear(self) -> None:
        """Clear all cached data."""
        self._cache.clear()
        logger.debug("Cache cleared")

    def clear_symbol(self, symbol: str) -> None:
        """Clear cached data for a specific symbol."""
        keys_to_remove = [k for k in self._cache.keys() if k.startswith(f"{symbol}:")]
        for key in keys_to_remove:
            del self._cache[key]
        logger.debug(f"Cleared cache for {symbol}")


class PriceDataFetcher:
    """
    Fetcher for historical price data from Finnhub API.

    Fetches OHLC candle data and converts it into PriceData format
    for use with volatility calculations.
    """

    def __init__(
        self,
        client: FinnhubClient,
        cache: Optional[PriceDataCache] = None,
        enable_cache: bool = True
    ):
        """
        Initialize price data fetcher.

        Args:
            client: FinnhubClient instance for API calls
            cache: Optional cache instance (creates new if None)
            enable_cache: Whether to use caching (default: True)
        """
        self.client = client
        self.enable_cache = enable_cache
        self.cache = cache if cache is not None else PriceDataCache()
        logger.debug(f"PriceDataFetcher initialized (caching={'enabled' if enable_cache else 'disabled'})")

    def fetch_price_data(
        self,
        symbol: str,
        lookback_days: int = 60,
        resolution: str = "D"
    ) -> PriceData:
        """
        Fetch historical price data for a symbol.

        Args:
            symbol: Stock ticker symbol (e.g., "F", "AAPL")
            lookback_days: Number of days of historical data (default: 60)
            resolution: Data resolution ("D" for daily, default: "D")

        Returns:
            PriceData with OHLC data

        Raises:
            FinnhubAPIError: If API call fails
            ValueError: If response is invalid or empty
        """
        symbol = symbol.upper()

        # Check cache first
        if self.enable_cache:
            cached_data = self.cache.get(symbol, lookback_days)
            if cached_data is not None:
                logger.info(f"Using cached price data for {symbol} ({lookback_days} days)")
                return cached_data

        # Calculate date range
        end_date = datetime.now()
        # Add extra days to account for weekends/holidays
        start_date = end_date - timedelta(days=int(lookback_days * 1.5))

        from_timestamp = int(start_date.timestamp())
        to_timestamp = int(end_date.timestamp())

        logger.info(
            f"Fetching {lookback_days} days of price data for {symbol} "
            f"from {start_date.date()} to {end_date.date()}"
        )

        # Fetch candle data from Finnhub
        try:
            response = self._call_candle_api(
                symbol=symbol,
                resolution=resolution,
                from_timestamp=from_timestamp,
                to_timestamp=to_timestamp
            )
        except FinnhubAPIError as e:
            logger.error(f"Failed to fetch price data for {symbol}: {e}")
            raise

        # Parse response
        price_data = self._parse_candle_response(response, symbol, lookback_days)

        # Cache the result
        if self.enable_cache:
            self.cache.set(symbol, lookback_days, price_data)

        return price_data

    def _call_candle_api(
        self,
        symbol: str,
        resolution: str,
        from_timestamp: int,
        to_timestamp: int
    ) -> Dict[str, Any]:
        """
        Call Finnhub candle API endpoint.

        Args:
            symbol: Stock ticker
            resolution: Data resolution
            from_timestamp: Start timestamp (Unix)
            to_timestamp: End timestamp (Unix)

        Returns:
            API response dictionary

        Raises:
            FinnhubAPIError: If API call fails
        """
        endpoint = "stock/candle"
        params = {
            "symbol": symbol,
            "resolution": resolution,
            "from": from_timestamp,
            "to": to_timestamp
        }

        try:
            response = self.client.session.get(
                f"{self.client.config.base_url}/{endpoint}",
                params=params,
                headers={"X-Finnhub-Token": self.client.config.api_key},
                timeout=self.client.config.timeout
            )
            response.raise_for_status()
            data = response.json()

            logger.debug(f"Candle API response status: {data.get('s', 'unknown')}")
            return data

        except Exception as e:
            raise FinnhubAPIError(f"Failed to fetch candle data: {e}")

    def _parse_candle_response(
        self,
        response: Dict[str, Any],
        symbol: str,
        requested_days: int
    ) -> PriceData:
        """
        Parse Finnhub candle response into PriceData.

        Finnhub returns arrays:
        - t: Unix timestamps
        - o: Open prices
        - h: High prices
        - l: Low prices
        - c: Close prices
        - v: Volumes

        Args:
            response: API response dictionary
            symbol: Stock ticker symbol
            requested_days: Number of days requested

        Returns:
            PriceData with parsed OHLC data

        Raises:
            ValueError: If response is invalid or empty
        """
        # Check status
        status = response.get("s")
        if status == "no_data":
            raise ValueError(f"No price data available for {symbol}")
        elif status != "ok":
            raise ValueError(f"Invalid response status: {status}")

        # Extract arrays
        timestamps = response.get("t", [])
        opens = response.get("o", [])
        highs = response.get("h", [])
        lows = response.get("l", [])
        closes = response.get("c", [])
        volumes = response.get("v", [])

        if not timestamps or not closes:
            raise ValueError(f"Empty price data for {symbol}")

        # Verify all arrays have same length
        lengths = [len(timestamps), len(opens), len(highs), len(lows), len(closes)]
        if len(set(lengths)) != 1:
            raise ValueError(f"Inconsistent data array lengths: {lengths}")

        # Convert timestamps to dates and filter to requested window
        dates = []
        filtered_opens = []
        filtered_highs = []
        filtered_lows = []
        filtered_closes = []
        filtered_volumes = []

        # Take the most recent N days
        n_points = min(len(timestamps), requested_days)
        start_idx = len(timestamps) - n_points

        for i in range(start_idx, len(timestamps)):
            date_str = datetime.fromtimestamp(timestamps[i]).strftime("%Y-%m-%d")
            dates.append(date_str)
            filtered_opens.append(round(opens[i], 2))
            filtered_highs.append(round(highs[i], 2))
            filtered_lows.append(round(lows[i], 2))
            filtered_closes.append(round(closes[i], 2))
            if volumes:
                filtered_volumes.append(int(volumes[i]))

        logger.info(
            f"Parsed {len(dates)} days of price data for {symbol} "
            f"({dates[0]} to {dates[-1]})"
        )

        # Validate data quality
        self._validate_price_data(filtered_opens, filtered_highs, filtered_lows, filtered_closes)

        return PriceData(
            dates=dates,
            opens=filtered_opens,
            highs=filtered_highs,
            lows=filtered_lows,
            closes=filtered_closes,
            volumes=filtered_volumes if filtered_volumes else None
        )

    def _validate_price_data(
        self,
        opens: list,
        highs: list,
        lows: list,
        closes: list
    ) -> None:
        """
        Validate price data quality.

        Args:
            opens: Opening prices
            highs: High prices
            lows: Low prices
            closes: Closing prices

        Raises:
            ValueError: If data quality issues detected
        """
        for i in range(len(opens)):
            # Check for non-positive prices
            if any(p <= 0 for p in [opens[i], highs[i], lows[i], closes[i]]):
                raise ValueError(f"Non-positive price detected at index {i}")

            # Check high >= low
            if highs[i] < lows[i]:
                raise ValueError(f"High < Low at index {i}: {highs[i]} < {lows[i]}")

            # Check extreme intraday moves (>50% is suspicious)
            if highs[i] / lows[i] > 1.5:
                logger.warning(
                    f"Large intraday range at index {i}: "
                    f"high={highs[i]}, low={lows[i]} ({highs[i]/lows[i]:.2f}x)"
                )

    def fetch_multiple_windows(
        self,
        symbol: str,
        windows: list = None
    ) -> Dict[int, PriceData]:
        """
        Fetch price data for multiple lookback windows.

        Useful for calculating volatility at different time horizons.

        Args:
            symbol: Stock ticker symbol
            windows: List of lookback periods in days (default: [20, 60, 252])

        Returns:
            Dictionary mapping window size to PriceData
        """
        if windows is None:
            windows = [20, 60, 252]

        results = {}
        for window in windows:
            try:
                price_data = self.fetch_price_data(symbol, lookback_days=window)
                results[window] = price_data
            except Exception as e:
                logger.warning(f"Failed to fetch {window}-day window for {symbol}: {e}")

        return results

    def clear_cache(self, symbol: Optional[str] = None) -> None:
        """
        Clear cached price data.

        Args:
            symbol: If provided, only clear data for this symbol.
                   If None, clear all cached data.
        """
        if symbol:
            self.cache.clear_symbol(symbol.upper())
        else:
            self.cache.clear()


class AlphaVantageRateLimitError(Exception):
    """Exception raised when Alpha Vantage daily rate limit is exceeded."""

    pass


class AlphaVantagePriceDataFetcher:
    """
    Fetcher for historical price data using Alpha Vantage API.

    Uses the TIME_SERIES_DAILY endpoint for OHLC + volume.
    API documentation: https://www.alphavantage.co/documentation/

    Free tier limits:
    - 25 requests/day
    - Max 100 data points per request (outputsize=compact)
    - outputsize=full requires premium subscription

    Note: Adjusted close, dividends, and splits require TIME_SERIES_DAILY_ADJUSTED
    which is a premium-only endpoint.
    """

    DAILY_LIMIT = 25  # Free tier daily API call limit
    MAX_LOOKBACK_DAYS = 100  # Free tier max data points (compact output)

    def __init__(
        self,
        config: "AlphaVantageConfig",
        cache: Optional[PriceDataCache] = None,
        enable_cache: bool = True,
        file_cache: Optional["LocalFileCache"] = None
    ):
        """
        Initialize Alpha Vantage price data fetcher.

        Args:
            config: AlphaVantageConfig instance with API credentials
            cache: Optional in-memory cache instance (creates new if None)
            enable_cache: Whether to use caching (default: True)
            file_cache: Optional LocalFileCache for persistent storage and usage tracking
        """
        # Import here to avoid circular imports
        from .config import AlphaVantageConfig

        self.config = config
        self.enable_cache = enable_cache
        self.cache = cache if cache is not None else PriceDataCache()
        self._file_cache = file_cache
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/json",
            "User-Agent": "AlphaVantagePriceDataFetcher/2.0"
        })
        logger.debug(
            f"AlphaVantagePriceDataFetcher initialized "
            f"(caching={'enabled' if enable_cache else 'disabled'}, "
            f"file_cache={'enabled' if file_cache else 'disabled'})"
        )

    def fetch_price_data(
        self,
        symbol: str,
        lookback_days: int = 60,
        resolution: str = "D"
    ) -> PriceData:
        """
        Fetch historical price data for a symbol from Alpha Vantage.

        Uses TIME_SERIES_DAILY to get OHLC + volume (free tier).

        Args:
            symbol: Stock ticker symbol (e.g., "F", "AAPL")
            lookback_days: Number of days of historical data (default: 60)
            resolution: Data resolution (only "D" for daily supported)

        Returns:
            PriceData with OHLC data and volumes.
            Note: adjusted_closes, dividends, split_coefficients will be None
            (require premium TIME_SERIES_DAILY_ADJUSTED endpoint)

        Raises:
            ValueError: If response is invalid or empty
            AlphaVantageRateLimitError: If daily rate limit exceeded
            FinnhubAPIError: If API call fails
        """
        symbol = symbol.upper()

        # Check in-memory cache first
        if self.enable_cache:
            cached_data = self.cache.get(symbol, lookback_days)
            if cached_data is not None:
                logger.info(f"Using in-memory cached price data for {symbol}")
                return cached_data

        # Check file-based cache (24-hour TTL for price data)
        file_cache_key = f"price_daily_{symbol}"
        if self._file_cache:
            cached_response = self._file_cache.get(file_cache_key, max_age_hours=24.0)
            if cached_response:
                logger.info(f"Using file-cached price data for {symbol}")
                price_data = self._parse_daily_response(
                    cached_response, symbol, lookback_days
                )
                if self.enable_cache:
                    self.cache.set(symbol, lookback_days, price_data)
                return price_data

        # Check API usage before making request
        if self._file_cache:
            usage = self._file_cache.get_alpha_vantage_usage_today()
            if usage >= self.DAILY_LIMIT:
                raise AlphaVantageRateLimitError(
                    f"Alpha Vantage daily limit reached ({usage}/{self.DAILY_LIMIT}). "
                    "Resets at midnight. Consider using cached data."
                )
            remaining = self.DAILY_LIMIT - usage
            if remaining <= 5:
                logger.warning(
                    f"Alpha Vantage API: {remaining} calls remaining today"
                )

        # Free tier limitation: compact returns max 100 data points
        # full output requires premium subscription
        if lookback_days > self.MAX_LOOKBACK_DAYS:
            logger.warning(
                f"Requested {lookback_days} days but free tier is limited to "
                f"{self.MAX_LOOKBACK_DAYS} days. Capping request."
            )
            lookback_days = self.MAX_LOOKBACK_DAYS

        logger.info(
            f"Fetching {lookback_days} days of price data for {symbol} "
            f"from Alpha Vantage (TIME_SERIES_DAILY)"
        )

        # Always use compact for free tier (max 100 data points)
        # outputsize=full requires premium subscription
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "apikey": self.config.api_key,
            "outputsize": "compact"
        }

        try:
            response = self._session.get(
                self.config.base_url,
                params=params,
                timeout=self.config.timeout
            )
            response.raise_for_status()
            data = response.json()

        except requests.exceptions.Timeout:
            raise FinnhubAPIError(
                f"Request timeout after {self.config.timeout}s for symbol {symbol}"
            )
        except requests.exceptions.RequestException as e:
            raise FinnhubAPIError(f"API request failed: {e}")

        # Increment usage counter after successful request
        if self._file_cache:
            new_usage = self._file_cache.increment_alpha_vantage_usage()
            logger.debug(f"Alpha Vantage API usage today: {new_usage}/{self.DAILY_LIMIT}")

        # Check for API errors
        if "Error Message" in data:
            raise ValueError(f"Alpha Vantage API error: {data['Error Message']}")

        if "Note" in data:
            # Rate limit message
            raise AlphaVantageRateLimitError(
                f"Alpha Vantage rate limit: {data['Note']}"
            )

        if "Information" in data:
            # Usually indicates API key issues or rate limits
            raise FinnhubAPIError(
                f"Alpha Vantage API info: {data['Information']}"
            )

        # Cache raw response to file (for future use without API call)
        if self._file_cache:
            self._file_cache.set(file_cache_key, data)

        # Parse the response
        price_data = self._parse_daily_response(data, symbol, lookback_days)

        # Cache in memory
        if self.enable_cache:
            self.cache.set(symbol, lookback_days, price_data)

        return price_data

    def _parse_daily_response(
        self,
        data: Dict[str, Any],
        symbol: str,
        lookback_days: int
    ) -> PriceData:
        """
        Parse TIME_SERIES_DAILY response into PriceData.

        Args:
            data: Raw API response dictionary
            symbol: Stock ticker symbol
            lookback_days: Number of days requested

        Returns:
            PriceData with OHLC and volume.
            adjusted_closes, dividends, split_coefficients are set to None
            (require premium TIME_SERIES_DAILY_ADJUSTED endpoint)
        """
        time_series = data.get("Time Series (Daily)")
        if not time_series:
            raise ValueError(f"No price data available for {symbol} from Alpha Vantage")

        # Convert to lists (dates are in reverse chronological order)
        all_dates = sorted(time_series.keys())  # Sort chronologically

        # Take the most recent N days
        if len(all_dates) > lookback_days:
            all_dates = all_dates[-lookback_days:]

        dates = []
        opens = []
        highs = []
        lows = []
        closes = []
        volumes = []

        for date_str in all_dates:
            day_data = time_series[date_str]
            dates.append(date_str)
            opens.append(round(float(day_data["1. open"]), 2))
            highs.append(round(float(day_data["2. high"]), 2))
            lows.append(round(float(day_data["3. low"]), 2))
            closes.append(round(float(day_data["4. close"]), 2))
            # TIME_SERIES_DAILY uses "5. volume"
            volumes.append(int(float(day_data["5. volume"])))

        logger.info(
            f"Parsed {len(dates)} days of price data for {symbol} "
            f"({dates[0]} to {dates[-1]})"
        )

        # Validate data
        self._validate_price_data(opens, highs, lows, closes)

        # Note: adjusted_closes, dividends, split_coefficients are None
        # because TIME_SERIES_DAILY (free tier) doesn't include them.
        # Premium TIME_SERIES_DAILY_ADJUSTED is required for that data.
        return PriceData(
            dates=dates,
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            adjusted_closes=None,
            volumes=volumes,
            dividends=None,
            split_coefficients=None
        )

    def _validate_price_data(
        self,
        opens: list,
        highs: list,
        lows: list,
        closes: list
    ) -> None:
        """Validate price data quality."""
        for i in range(len(opens)):
            if any(p <= 0 for p in [opens[i], highs[i], lows[i], closes[i]]):
                raise ValueError(f"Non-positive price detected at index {i}")

            if highs[i] < lows[i]:
                raise ValueError(f"High < Low at index {i}: {highs[i]} < {lows[i]}")

            if highs[i] / lows[i] > 1.5:
                logger.warning(
                    f"Large intraday range at index {i}: "
                    f"high={highs[i]}, low={lows[i]} ({highs[i]/lows[i]:.2f}x)"
                )

    def fetch_multiple_windows(
        self,
        symbol: str,
        windows: Optional[list] = None
    ) -> Dict[int, PriceData]:
        """
        Fetch price data for multiple lookback windows.

        Args:
            symbol: Stock ticker symbol
            windows: List of lookback periods in days (default: [20, 60, 252])

        Returns:
            Dictionary mapping window size to PriceData
        """
        if windows is None:
            windows = [20, 60, 252]

        results = {}
        for window in windows:
            try:
                price_data = self.fetch_price_data(symbol, lookback_days=window)
                results[window] = price_data
            except Exception as e:
                logger.warning(f"Failed to fetch {window}-day window for {symbol}: {e}")

        return results

    def clear_cache(self, symbol: Optional[str] = None) -> None:
        """Clear cached price data."""
        if symbol:
            self.cache.clear_symbol(symbol.upper())
        else:
            self.cache.clear()

    def get_usage_status(self) -> Dict[str, Any]:
        """
        Get current Alpha Vantage API usage status.

        Returns:
            Dictionary with usage information:
            - calls_today: Number of API calls made today
            - daily_limit: Maximum allowed calls per day
            - remaining: Calls remaining today
            - percentage_used: Percentage of daily limit used
        """
        if self._file_cache:
            usage = self._file_cache.get_alpha_vantage_usage_today()
        else:
            usage = 0

        return {
            "calls_today": usage,
            "daily_limit": self.DAILY_LIMIT,
            "remaining": self.DAILY_LIMIT - usage,
            "percentage_used": (usage / self.DAILY_LIMIT) * 100
        }

    def close(self) -> None:
        """Close the HTTP session."""
        self._session.close()
        logger.debug("AlphaVantagePriceDataFetcher session closed")

    def __enter__(self) -> "AlphaVantagePriceDataFetcher":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - ensures cleanup."""
        self.close()
