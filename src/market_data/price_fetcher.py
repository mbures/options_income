"""
Price data fetcher with caching layer.

This module provides high-level price data fetchers with in-memory caching.

Data Providers:
1. **Schwab API** (via SchwabClient) - PRIMARY
   - Uses /marketdata/v1/pricehistory endpoint
   - Returns OHLC data with volume
   - Requires Schwab OAuth authentication
   - Rate limit: 120 requests/minute

2. **Finnhub API** (via FinnhubClient) - LEGACY
   - Uses /stock/candle endpoint
   - IMPORTANT: Requires paid Finnhub subscription for price data
   - Free tier will return 403 Forbidden error
   - Deprecated - will be removed in future version

Usage:
    # Schwab (recommended)
    from src.schwab.client import SchwabClient
    from src.price_fetcher import SchwabPriceDataFetcher

    schwab = SchwabClient(oauth_coordinator)
    fetcher = SchwabPriceDataFetcher(schwab)
    price_data = fetcher.fetch_price_data("AAPL", lookback_days=60)

All fetchers return PriceData objects compatible with the volatility calculator.
"""

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from src.market_data.finnhub_client import FinnhubClient
from src.analysis.volatility import PriceData

if TYPE_CHECKING:
    from .cache import LocalFileCache

logger = logging.getLogger(__name__)


# =============================================================================
# Shared Caching Utilities
# =============================================================================


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
        self._cache: dict[str, CacheEntry] = {}
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
            data=data, timestamp=time.time(), symbol=symbol, lookback_days=lookback_days
        )
        logger.debug(f"Cached price data for {cache_key}")

    def clear(self) -> None:
        """Clear all cached data."""
        self._cache.clear()
        logger.debug("Cache cleared")

    def clear_symbol(self, symbol: str) -> None:
        """Clear cached data for a specific symbol."""
        keys_to_remove = [k for k in self._cache if k.startswith(f"{symbol}:")]
        for key in keys_to_remove:
            del self._cache[key]
        logger.debug(f"Cleared cache for {symbol}")


# =============================================================================
# Finnhub Price Data Fetcher (with caching)
# =============================================================================


class PriceDataFetcher:
    """
    Fetcher for historical price data from Finnhub API with caching.

    Wraps FinnhubClient to add in-memory caching capabilities.

    Note: Finnhub candle data requires a paid subscription for most symbols.
    """

    def __init__(
        self,
        client: FinnhubClient,
        cache: Optional[PriceDataCache] = None,
        enable_cache: bool = True,
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
        logger.debug(
            f"PriceDataFetcher initialized (caching={'enabled' if enable_cache else 'disabled'})"
        )

    def fetch_price_data(
        self, symbol: str, lookback_days: int = 60, resolution: str = "D"
    ) -> PriceData:
        """
        Fetch historical price data for a symbol.

        Args:
            symbol: Stock ticker symbol (e.g., "F", "AAPL")
            lookback_days: Number of days of historical data (default: 60)
            resolution: Data resolution ("D" for daily)

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

        # Fetch from Finnhub
        price_data = self.client.get_candle_data(symbol, lookback_days, resolution)

        # Cache the result
        if self.enable_cache:
            self.cache.set(symbol, lookback_days, price_data)

        return price_data

    def fetch_multiple_windows(self, symbol: str, windows: list = None) -> dict[int, PriceData]:
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


# =============================================================================
# Schwab Price Data Fetcher (with caching)
# =============================================================================


class SchwabPriceDataFetcher:
    """
    Fetcher for historical price data from Schwab API with caching.

    Wraps SchwabClient to add in-memory caching capabilities.
    This is the recommended price fetcher - Schwab is the primary data provider.
    """

    def __init__(
        self,
        schwab_client,
        cache: Optional[PriceDataCache] = None,
        enable_cache: bool = True,
    ):
        """
        Initialize Schwab price data fetcher.

        Args:
            schwab_client: SchwabClient instance for API calls
            cache: Optional in-memory cache instance (creates new if None)
            enable_cache: Whether to use caching (default: True)
        """
        self._client = schwab_client
        self.enable_cache = enable_cache
        self.cache = cache if cache is not None else PriceDataCache()
        logger.debug(
            f"SchwabPriceDataFetcher initialized "
            f"(caching={'enabled' if enable_cache else 'disabled'})"
        )

    def fetch_price_data(
        self, symbol: str, lookback_days: int = 60, resolution: str = "D"
    ) -> PriceData:
        """
        Fetch historical price data for a symbol from Schwab.

        Args:
            symbol: Stock ticker symbol (e.g., "AAPL")
            lookback_days: Number of days of historical data (default: 60)
            resolution: Data resolution ("D" for daily - only daily supported)

        Returns:
            PriceData with OHLCV data

        Raises:
            SchwabAPIError: If API call fails
            SchwabAuthenticationError: If not authenticated
        """
        symbol = symbol.upper()

        # Check in-memory cache first
        if self.enable_cache:
            cached_data = self.cache.get(symbol, lookback_days)
            if cached_data is not None:
                logger.info(f"Using in-memory cached price data for {symbol}")
                return cached_data

        # Convert lookback_days to Schwab API parameters
        period_type, period = self._lookback_to_schwab_params(lookback_days)

        # Fetch from Schwab client
        price_data = self._client.get_price_history(
            symbol=symbol,
            period_type=period_type,
            period=period,
            frequency_type="daily",
            frequency=1,
        )

        # Cache in memory
        if self.enable_cache:
            self.cache.set(symbol, lookback_days, price_data)

        return price_data

    def get_current_price(self, symbol: str) -> float:
        """
        Get current price for a symbol from Schwab.

        Args:
            symbol: Stock ticker symbol (e.g., "AAPL")

        Returns:
            Current price (lastPrice or closePrice)

        Raises:
            SchwabAPIError: If API call fails
            SchwabAuthenticationError: If not authenticated
            ValueError: If no price data available in quote
        """
        symbol = symbol.upper()

        # Get quote from Schwab (respects its own 5-minute cache)
        quote = self._client.get_quote(symbol)

        # Try multiple price fields in order of preference
        price = (
            quote.get("lastPrice")
            or quote.get("closePrice")
            or quote.get("bidPrice")  # Fallback to bid if no last/close
        )

        if price is None:
            raise ValueError(f"No price data available in quote for {symbol}")

        return float(price)

    def _lookback_to_schwab_params(self, lookback_days: int) -> tuple[str, int]:
        """
        Convert lookback_days to Schwab period_type and period.

        Schwab API period options:
        - day: 1, 2, 3, 4, 5, 10 (frequencyType must be "minute")
        - month: 1, 2, 3, 6 (frequencyType can be "daily" or "weekly")
        - year: 1, 2, 3, 5, 10, 15, 20 (frequencyType can be "daily", "weekly", "monthly")
        - ytd: 1

        Since we need daily OHLC data, we avoid periodType="day" (which only supports minute data).

        Args:
            lookback_days: Number of days of data requested

        Returns:
            Tuple of (period_type, period)
        """
        # Always use month/year periods to get daily data
        # periodType="day" only supports minute frequency, so we avoid it
        if lookback_days <= 30:
            return ("month", 1)
        elif lookback_days <= 60:
            return ("month", 2)
        elif lookback_days <= 90:
            return ("month", 3)
        elif lookback_days <= 180:
            return ("month", 6)
        elif lookback_days <= 365:
            return ("year", 1)
        elif lookback_days <= 730:
            return ("year", 2)
        elif lookback_days <= 1095:
            return ("year", 3)
        elif lookback_days <= 1825:
            return ("year", 5)
        else:
            return ("year", 10)

    def fetch_multiple_windows(
        self, symbol: str, windows: Optional[list] = None
    ) -> dict[int, PriceData]:
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
