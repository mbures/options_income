"""Unit tests for price data fetcher module."""

import pytest
import time
from unittest.mock import Mock, patch
from datetime import datetime

from src.price_fetcher import (
    PriceDataFetcher,
    PriceDataCache,
    CacheEntry,
    AlphaVantagePriceDataFetcher
)
from src.volatility import PriceData
from src.finnhub_client import FinnhubClient, FinnhubAPIError


class TestCacheEntry:
    """Test suite for CacheEntry class."""

    def test_cache_entry_creation(self):
        """Test cache entry creation."""
        price_data = PriceData(dates=["2026-01-01"], closes=[100.0])
        entry = CacheEntry(
            data=price_data,
            timestamp=time.time(),
            symbol="F",
            lookback_days=60
        )

        assert entry.symbol == "F"
        assert entry.lookback_days == 60
        assert entry.data == price_data

    def test_cache_entry_is_valid_fresh(self):
        """Test that fresh cache entry is valid."""
        price_data = PriceData(dates=["2026-01-01"], closes=[100.0])
        entry = CacheEntry(
            data=price_data,
            timestamp=time.time(),
            symbol="F",
            lookback_days=60
        )

        assert entry.is_valid(max_age_seconds=3600)

    def test_cache_entry_is_valid_expired(self):
        """Test that expired cache entry is invalid."""
        price_data = PriceData(dates=["2026-01-01"], closes=[100.0])
        entry = CacheEntry(
            data=price_data,
            timestamp=time.time() - 7200,  # 2 hours ago
            symbol="F",
            lookback_days=60
        )

        assert not entry.is_valid(max_age_seconds=3600)  # 1 hour max age


class TestPriceDataCache:
    """Test suite for PriceDataCache class."""

    def test_cache_initialization(self):
        """Test cache initialization."""
        cache = PriceDataCache(max_age_seconds=1800)
        assert cache.max_age_seconds == 1800
        assert len(cache._cache) == 0

    def test_cache_set_and_get(self):
        """Test setting and getting cached data."""
        cache = PriceDataCache()
        price_data = PriceData(dates=["2026-01-01"], closes=[100.0])

        # Set data
        cache.set("F", 60, price_data)

        # Get data
        retrieved = cache.get("F", 60)
        assert retrieved is not None
        assert retrieved.dates == ["2026-01-01"]
        assert retrieved.closes == [100.0]

    def test_cache_miss(self):
        """Test cache miss for non-existent data."""
        cache = PriceDataCache()

        retrieved = cache.get("AAPL", 60)
        assert retrieved is None

    def test_cache_different_windows(self):
        """Test that different windows are cached separately."""
        cache = PriceDataCache()

        data_20 = PriceData(dates=["2026-01-01"], closes=[100.0])
        data_60 = PriceData(dates=["2025-12-01"], closes=[95.0])

        cache.set("F", 20, data_20)
        cache.set("F", 60, data_60)

        retrieved_20 = cache.get("F", 20)
        retrieved_60 = cache.get("F", 60)

        assert retrieved_20.closes == [100.0]
        assert retrieved_60.closes == [95.0]

    def test_cache_clear(self):
        """Test clearing all cache."""
        cache = PriceDataCache()
        price_data = PriceData(dates=["2026-01-01"], closes=[100.0])

        cache.set("F", 60, price_data)
        cache.set("AAPL", 60, price_data)

        cache.clear()

        assert cache.get("F", 60) is None
        assert cache.get("AAPL", 60) is None

    def test_cache_clear_symbol(self):
        """Test clearing cache for specific symbol."""
        cache = PriceDataCache()
        price_data = PriceData(dates=["2026-01-01"], closes=[100.0])

        cache.set("F", 20, price_data)
        cache.set("F", 60, price_data)
        cache.set("AAPL", 60, price_data)

        cache.clear_symbol("F")

        assert cache.get("F", 20) is None
        assert cache.get("F", 60) is None
        assert cache.get("AAPL", 60) is not None


class TestPriceDataFetcher:
    """Test suite for PriceDataFetcher class (caching layer)."""

    def create_mock_client(self):
        """Create a mock FinnhubClient."""
        client = Mock(spec=FinnhubClient)
        client.config = Mock()
        client.config.base_url = "https://finnhub.io/api/v1"
        client.config.api_key = "test_key"
        client.config.timeout = 10
        return client

    def create_mock_price_data(self, n_days=60):
        """Create mock PriceData."""
        base_date = datetime(2026, 1, 1)
        dates = [(base_date.replace(day=1+i)).strftime("%Y-%m-%d") for i in range(min(n_days, 28))]
        if n_days > 28:
            dates = [f"2026-01-{str(i+1).zfill(2)}" for i in range(n_days)]

        return PriceData(
            dates=dates,
            opens=[100.0 + i * 0.1 for i in range(n_days)],
            highs=[102.0 + i * 0.1 for i in range(n_days)],
            lows=[99.0 + i * 0.1 for i in range(n_days)],
            closes=[101.0 + i * 0.1 for i in range(n_days)],
            volumes=[1000000 + i * 1000 for i in range(n_days)]
        )

    def test_fetcher_initialization(self):
        """Test fetcher initialization."""
        client = self.create_mock_client()
        fetcher = PriceDataFetcher(client)

        assert fetcher.client == client
        assert fetcher.enable_cache is True
        assert fetcher.cache is not None

    def test_fetcher_with_custom_cache(self):
        """Test fetcher with custom cache."""
        client = self.create_mock_client()
        custom_cache = PriceDataCache(max_age_seconds=1800)
        fetcher = PriceDataFetcher(client, cache=custom_cache)

        assert fetcher.cache == custom_cache
        assert fetcher.cache.max_age_seconds == 1800

    def test_fetch_price_data_success(self):
        """Test successful price data fetch."""
        client = self.create_mock_client()
        fetcher = PriceDataFetcher(client, enable_cache=False)

        # Mock client.get_candle_data to return PriceData
        mock_price_data = self.create_mock_price_data(60)
        client.get_candle_data.return_value = mock_price_data

        # Fetch data
        price_data = fetcher.fetch_price_data("F", lookback_days=60)

        assert isinstance(price_data, PriceData)
        assert len(price_data.dates) == 60
        assert len(price_data.closes) == 60
        client.get_candle_data.assert_called_once_with("F", 60, "D")

    def test_fetch_price_data_uses_cache(self):
        """Test that fetcher uses cached data."""
        client = self.create_mock_client()
        fetcher = PriceDataFetcher(client, enable_cache=True)

        # Mock client.get_candle_data
        mock_price_data = self.create_mock_price_data(60)
        client.get_candle_data.return_value = mock_price_data

        # First fetch - should hit client
        price_data_1 = fetcher.fetch_price_data("F", lookback_days=60)
        assert client.get_candle_data.call_count == 1

        # Second fetch - should use cache
        price_data_2 = fetcher.fetch_price_data("F", lookback_days=60)
        assert client.get_candle_data.call_count == 1  # Still 1, no new call

        # Data should be identical
        assert price_data_1.dates == price_data_2.dates

    def test_fetch_price_data_no_data(self):
        """Test handling of no data response."""
        client = self.create_mock_client()
        fetcher = PriceDataFetcher(client, enable_cache=False)

        # Mock client to raise ValueError
        client.get_candle_data.side_effect = ValueError("No price data available for INVALID")

        with pytest.raises(ValueError, match="No price data available"):
            fetcher.fetch_price_data("INVALID")

    def test_fetch_price_data_api_error(self):
        """Test handling of API errors."""
        client = self.create_mock_client()
        fetcher = PriceDataFetcher(client, enable_cache=False)

        # Mock client to raise FinnhubAPIError
        client.get_candle_data.side_effect = FinnhubAPIError("Failed to fetch candle data")

        with pytest.raises(FinnhubAPIError, match="Failed to fetch candle data"):
            fetcher.fetch_price_data("F")

    def test_fetch_multiple_windows(self):
        """Test fetching multiple lookback windows."""
        client = self.create_mock_client()
        fetcher = PriceDataFetcher(client, enable_cache=False)

        # Mock client.get_candle_data to return different data for different windows
        def mock_get_candle_data(symbol, lookback_days, resolution):
            return self.create_mock_price_data(lookback_days)

        client.get_candle_data.side_effect = mock_get_candle_data

        results = fetcher.fetch_multiple_windows("F", windows=[20, 60])

        assert 20 in results
        assert 60 in results
        assert len(results[20].dates) == 20
        assert len(results[60].dates) == 60

    def test_clear_cache(self):
        """Test clearing cache."""
        client = self.create_mock_client()
        fetcher = PriceDataFetcher(client)

        # Add some data to cache
        price_data = PriceData(dates=["2026-01-01"], closes=[100.0])
        fetcher.cache.set("F", 60, price_data)

        fetcher.clear_cache()

        assert fetcher.cache.get("F", 60) is None

    def test_clear_cache_specific_symbol(self):
        """Test clearing cache for specific symbol."""
        client = self.create_mock_client()
        fetcher = PriceDataFetcher(client)

        # Add data for multiple symbols
        price_data = PriceData(dates=["2026-01-01"], closes=[100.0])
        fetcher.cache.set("F", 60, price_data)
        fetcher.cache.set("AAPL", 60, price_data)

        fetcher.clear_cache("F")

        assert fetcher.cache.get("F", 60) is None
        assert fetcher.cache.get("AAPL", 60) is not None

    def test_symbol_normalization(self):
        """Test that symbols are normalized to uppercase."""
        client = self.create_mock_client()
        fetcher = PriceDataFetcher(client, enable_cache=False)

        mock_price_data = self.create_mock_price_data(20)
        client.get_candle_data.return_value = mock_price_data

        # Fetch with lowercase symbol
        fetcher.fetch_price_data("aapl", lookback_days=20)

        # Verify client was called with uppercase
        client.get_candle_data.assert_called_once_with("AAPL", 20, "D")


class TestAlphaVantagePriceDataFetcher:
    """Test suite for AlphaVantagePriceDataFetcher class."""

    def create_mock_client(self):
        """Create a mock AlphaVantageClient."""
        from src.alphavantage_client import AlphaVantageClient
        client = Mock(spec=AlphaVantageClient)
        client.config = Mock()
        client.config.base_url = "https://www.alphavantage.co/query"
        client.config.api_key = "test_key"
        client.DAILY_LIMIT = 25
        client.MAX_LOOKBACK_DAYS = 100
        return client

    def create_mock_price_data(self, n_days=60):
        """Create mock PriceData."""
        dates = [f"2026-01-{str(i+1).zfill(2)}" for i in range(n_days)]
        return PriceData(
            dates=dates,
            opens=[100.0 + i * 0.1 for i in range(n_days)],
            highs=[102.0 + i * 0.1 for i in range(n_days)],
            lows=[99.0 + i * 0.1 for i in range(n_days)],
            closes=[101.0 + i * 0.1 for i in range(n_days)],
            volumes=[1000000 + i * 1000 for i in range(n_days)],
            adjusted_closes=None,
            dividends=None,
            split_coefficients=None
        )

    def test_fetcher_initialization_with_client(self):
        """Test fetcher initialization with client."""
        client = self.create_mock_client()
        fetcher = AlphaVantagePriceDataFetcher(client)

        assert fetcher._client == client
        assert fetcher.enable_cache is True

    def test_fetch_price_data_success(self):
        """Test successful price data fetch."""
        client = self.create_mock_client()
        fetcher = AlphaVantagePriceDataFetcher(client, enable_cache=False)

        mock_price_data = self.create_mock_price_data(60)
        client.fetch_daily_prices.return_value = mock_price_data

        price_data = fetcher.fetch_price_data("F", lookback_days=60)

        assert isinstance(price_data, PriceData)
        assert len(price_data.dates) == 60
        client.fetch_daily_prices.assert_called_once_with("F", 60)

    def test_fetch_price_data_uses_cache(self):
        """Test that fetcher uses cached data."""
        client = self.create_mock_client()
        fetcher = AlphaVantagePriceDataFetcher(client, enable_cache=True)

        mock_price_data = self.create_mock_price_data(60)
        client.fetch_daily_prices.return_value = mock_price_data

        # First fetch
        fetcher.fetch_price_data("F", lookback_days=60)
        assert client.fetch_daily_prices.call_count == 1

        # Second fetch - should use cache
        fetcher.fetch_price_data("F", lookback_days=60)
        assert client.fetch_daily_prices.call_count == 1

    def test_get_usage_status(self):
        """Test getting API usage status."""
        client = self.create_mock_client()
        client.get_usage_status.return_value = {
            "calls_today": 5,
            "daily_limit": 25,
            "remaining": 20,
            "percentage_used": 20.0
        }

        fetcher = AlphaVantagePriceDataFetcher(client)
        status = fetcher.get_usage_status()

        assert status["calls_today"] == 5
        assert status["remaining"] == 20
        client.get_usage_status.assert_called_once()

    def test_symbol_normalization(self):
        """Test that symbols are normalized to uppercase."""
        client = self.create_mock_client()
        fetcher = AlphaVantagePriceDataFetcher(client, enable_cache=False)

        mock_price_data = self.create_mock_price_data(20)
        client.fetch_daily_prices.return_value = mock_price_data

        fetcher.fetch_price_data("aapl", lookback_days=20)

        client.fetch_daily_prices.assert_called_once_with("AAPL", 20)
