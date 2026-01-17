"""
Price data fetcher with caching layer.

This module provides high-level price data fetchers with in-memory caching.
It wraps the low-level API clients (FinnhubClient, AlphaVantageClient) to
provide a consistent interface with caching capabilities.

Data Providers:
1. **Finnhub API** (via FinnhubClient)
   - Uses /stock/candle endpoint
   - IMPORTANT: Requires paid Finnhub subscription for price data
   - Free tier will return 403 Forbidden error

2. **Alpha Vantage API** (via AlphaVantageClient)
   - Uses TIME_SERIES_DAILY endpoint (free tier)
   - Returns OHLC data with volume
   - Free tier limits: 25 requests/day, max 100 data points per request

Usage:
    # Option 1: Finnhub (requires premium API key)
    from src.finnhub_client import FinnhubClient
    from src.price_fetcher import PriceDataFetcher

    client = FinnhubClient(config)
    fetcher = PriceDataFetcher(client)
    price_data = fetcher.fetch_price_data("AAPL", lookback_days=60)

    # Option 2: Alpha Vantage (free tier, recommended)
    from src.alphavantage_client import AlphaVantageClient
    from src.price_fetcher import AlphaVantagePriceDataFetcher

    client = AlphaVantageClient(config, file_cache=file_cache)
    fetcher = AlphaVantagePriceDataFetcher(client)
    price_data = fetcher.fetch_price_data("AAPL", lookback_days=60)

Both fetchers return PriceData objects compatible with the volatility calculator.
"""

import logging
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass

from .volatility import PriceData
from .finnhub_client import FinnhubClient, FinnhubAPIError
from .alphavantage_client import (
    AlphaVantageClient,
    AlphaVantageAPIError,
    AlphaVantageRateLimitError
)

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
        logger.debug(
            f"PriceDataFetcher initialized "
            f"(caching={'enabled' if enable_cache else 'disabled'})"
        )

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

    def fetch_multiple_windows(
        self,
        symbol: str,
        windows: list = None
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
# Alpha Vantage Price Data Fetcher (with caching)
# =============================================================================


class AlphaVantagePriceDataFetcher:
    """
    Fetcher for historical price data from Alpha Vantage API with caching.

    Wraps AlphaVantageClient to add in-memory caching capabilities.

    Free tier limits:
    - 25 requests/day
    - Max 100 data points per request (outputsize=compact)
    """

    # Expose class constants for convenience
    DAILY_LIMIT = AlphaVantageClient.DAILY_LIMIT
    MAX_LOOKBACK_DAYS = AlphaVantageClient.MAX_LOOKBACK_DAYS

    def __init__(
        self,
        config_or_client,
        cache: Optional[PriceDataCache] = None,
        enable_cache: bool = True,
        file_cache: Optional["LocalFileCache"] = None
    ):
        """
        Initialize Alpha Vantage price data fetcher.

        Args:
            config_or_client: Either an AlphaVantageConfig or AlphaVantageClient instance
            cache: Optional in-memory cache instance (creates new if None)
            enable_cache: Whether to use caching (default: True)
            file_cache: Optional LocalFileCache for persistent storage (used if config passed)
        """
        # Support both old API (config) and new API (client)
        if isinstance(config_or_client, AlphaVantageClient):
            self._client = config_or_client
        else:
            # Assume it's a config, create client
            self._client = AlphaVantageClient(config_or_client, file_cache=file_cache)

        self.enable_cache = enable_cache
        self.cache = cache if cache is not None else PriceDataCache()
        logger.debug(
            f"AlphaVantagePriceDataFetcher initialized "
            f"(caching={'enabled' if enable_cache else 'disabled'})"
        )

    @property
    def config(self):
        """Access the underlying client's config."""
        return self._client.config

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
            AlphaVantageAPIError: If API call fails
        """
        symbol = symbol.upper()

        # Check in-memory cache first
        if self.enable_cache:
            cached_data = self.cache.get(symbol, lookback_days)
            if cached_data is not None:
                logger.info(f"Using in-memory cached price data for {symbol}")
                return cached_data

        # Fetch from Alpha Vantage client
        price_data = self._client.fetch_daily_prices(symbol, lookback_days)

        # Cache in memory
        if self.enable_cache:
            self.cache.set(symbol, lookback_days, price_data)

        return price_data

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
            Dictionary with usage information
        """
        return self._client.get_usage_status()

    def close(self) -> None:
        """Close the underlying client's HTTP session."""
        self._client.close()
        logger.debug("AlphaVantagePriceDataFetcher session closed")

    def __enter__(self) -> "AlphaVantagePriceDataFetcher":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - ensures cleanup."""
        self.close()
