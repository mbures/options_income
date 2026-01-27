"""Unit tests for price data fetcher module."""

import time
from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from src.finnhub_client import FinnhubAPIError, FinnhubClient
from src.price_fetcher import (
    CacheEntry,
    PriceDataCache,
    PriceDataFetcher,
    SchwabPriceDataFetcher,
)
from src.volatility import PriceData


class TestCacheEntry:
    """Test suite for CacheEntry class."""

    def test_cache_entry_creation(self):
        """Test cache entry creation."""
        price_data = PriceData(dates=["2026-01-01"], closes=[100.0])
        entry = CacheEntry(data=price_data, timestamp=time.time(), symbol="F", lookback_days=60)

        assert entry.symbol == "F"
        assert entry.lookback_days == 60
        assert entry.data == price_data

    def test_cache_entry_is_valid_fresh(self):
        """Test that fresh cache entry is valid."""
        price_data = PriceData(dates=["2026-01-01"], closes=[100.0])
        entry = CacheEntry(data=price_data, timestamp=time.time(), symbol="F", lookback_days=60)

        assert entry.is_valid(max_age_seconds=3600)

    def test_cache_entry_is_valid_expired(self):
        """Test that expired cache entry is invalid."""
        price_data = PriceData(dates=["2026-01-01"], closes=[100.0])
        entry = CacheEntry(
            data=price_data,
            timestamp=time.time() - 7200,  # 2 hours ago
            symbol="F",
            lookback_days=60,
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
        dates = [
            (base_date.replace(day=1 + i)).strftime("%Y-%m-%d") for i in range(min(n_days, 28))
        ]
        if n_days > 28:
            dates = [f"2026-01-{str(i + 1).zfill(2)}" for i in range(n_days)]

        return PriceData(
            dates=dates,
            opens=[100.0 + i * 0.1 for i in range(n_days)],
            highs=[102.0 + i * 0.1 for i in range(n_days)],
            lows=[99.0 + i * 0.1 for i in range(n_days)],
            closes=[101.0 + i * 0.1 for i in range(n_days)],
            volumes=[1000000 + i * 1000 for i in range(n_days)],
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


class TestSchwabPriceDataFetcher:
    """Test suite for SchwabPriceDataFetcher class."""

    def create_mock_schwab_client(self):
        """Create a mock SchwabClient."""
        from src.schwab.client import SchwabClient

        client = Mock(spec=SchwabClient)
        return client

    def create_mock_price_data(self, n_days=60):
        """Create mock PriceData."""
        dates = [f"2026-01-{str(i + 1).zfill(2)}" for i in range(n_days)]
        return PriceData(
            dates=dates,
            opens=[100.0 + i * 0.1 for i in range(n_days)],
            highs=[102.0 + i * 0.1 for i in range(n_days)],
            lows=[99.0 + i * 0.1 for i in range(n_days)],
            closes=[101.0 + i * 0.1 for i in range(n_days)],
            volumes=[1000000 + i * 1000 for i in range(n_days)],
        )

    def test_fetcher_initialization(self):
        """Test fetcher initialization with Schwab client."""
        client = self.create_mock_schwab_client()
        fetcher = SchwabPriceDataFetcher(client)

        assert fetcher._client == client
        assert fetcher.enable_cache is True
        assert fetcher.cache is not None

    def test_fetcher_with_custom_cache(self):
        """Test fetcher with custom cache."""
        client = self.create_mock_schwab_client()
        custom_cache = PriceDataCache(max_age_seconds=1800)
        fetcher = SchwabPriceDataFetcher(client, cache=custom_cache)

        assert fetcher.cache == custom_cache
        assert fetcher.cache.max_age_seconds == 1800

    def test_fetch_price_data_success(self):
        """Test successful price data fetch from Schwab."""
        client = self.create_mock_schwab_client()
        fetcher = SchwabPriceDataFetcher(client, enable_cache=False)

        mock_price_data = self.create_mock_price_data(60)
        client.get_price_history.return_value = mock_price_data

        price_data = fetcher.fetch_price_data("AAPL", lookback_days=60)

        assert isinstance(price_data, PriceData)
        assert len(price_data.dates) == 60
        assert len(price_data.closes) == 60

    def test_fetch_price_data_uses_cache(self):
        """Test that fetcher uses cached data."""
        client = self.create_mock_schwab_client()
        fetcher = SchwabPriceDataFetcher(client, enable_cache=True)

        mock_price_data = self.create_mock_price_data(60)
        client.get_price_history.return_value = mock_price_data

        # First fetch - should hit client
        fetcher.fetch_price_data("AAPL", lookback_days=60)
        assert client.get_price_history.call_count == 1

        # Second fetch - should use cache
        fetcher.fetch_price_data("AAPL", lookback_days=60)
        assert client.get_price_history.call_count == 1  # Still 1, no new call

    def test_lookback_to_schwab_params_short(self):
        """Test conversion of short lookback to Schwab parameters."""
        client = self.create_mock_schwab_client()
        fetcher = SchwabPriceDataFetcher(client)

        # 5 days -> day, 5
        period_type, period = fetcher._lookback_to_schwab_params(5)
        assert period_type == "day"
        assert period == 5

        # 10 days -> day, 10
        period_type, period = fetcher._lookback_to_schwab_params(10)
        assert period_type == "day"
        assert period == 10

    def test_lookback_to_schwab_params_medium(self):
        """Test conversion of medium lookback to Schwab parameters."""
        client = self.create_mock_schwab_client()
        fetcher = SchwabPriceDataFetcher(client)

        # 20 days -> month, 1
        period_type, period = fetcher._lookback_to_schwab_params(20)
        assert period_type == "month"
        assert period == 1

        # 60 days -> month, 2
        period_type, period = fetcher._lookback_to_schwab_params(60)
        assert period_type == "month"
        assert period == 2

        # 90 days -> month, 3
        period_type, period = fetcher._lookback_to_schwab_params(90)
        assert period_type == "month"
        assert period == 3

    def test_lookback_to_schwab_params_long(self):
        """Test conversion of long lookback to Schwab parameters."""
        client = self.create_mock_schwab_client()
        fetcher = SchwabPriceDataFetcher(client)

        # 252 days (1 trading year) -> year, 1
        period_type, period = fetcher._lookback_to_schwab_params(252)
        assert period_type == "year"
        assert period == 1

        # 500 days -> year, 2
        period_type, period = fetcher._lookback_to_schwab_params(500)
        assert period_type == "year"
        assert period == 2

    def test_fetch_price_data_calls_schwab_with_correct_params(self):
        """Test that Schwab client is called with converted parameters."""
        client = self.create_mock_schwab_client()
        fetcher = SchwabPriceDataFetcher(client, enable_cache=False)

        mock_price_data = self.create_mock_price_data(60)
        client.get_price_history.return_value = mock_price_data

        fetcher.fetch_price_data("AAPL", lookback_days=60)

        client.get_price_history.assert_called_once_with(
            symbol="AAPL",
            period_type="month",
            period=2,
            frequency_type="daily",
            frequency=1,
        )

    def test_fetch_multiple_windows(self):
        """Test fetching multiple lookback windows."""
        client = self.create_mock_schwab_client()
        fetcher = SchwabPriceDataFetcher(client, enable_cache=False)

        def mock_get_price_history(symbol, period_type, period, frequency_type, frequency):
            # Return mock data based on period
            if period_type == "month" and period == 1:
                return self.create_mock_price_data(20)
            elif period_type == "month" and period == 2:
                return self.create_mock_price_data(60)
            return self.create_mock_price_data(10)

        client.get_price_history.side_effect = mock_get_price_history

        results = fetcher.fetch_multiple_windows("AAPL", windows=[20, 60])

        assert 20 in results
        assert 60 in results

    def test_clear_cache(self):
        """Test clearing cache."""
        client = self.create_mock_schwab_client()
        fetcher = SchwabPriceDataFetcher(client)

        # Add some data to cache
        price_data = PriceData(dates=["2026-01-01"], closes=[100.0])
        fetcher.cache.set("AAPL", 60, price_data)

        fetcher.clear_cache()

        assert fetcher.cache.get("AAPL", 60) is None

    def test_clear_cache_specific_symbol(self):
        """Test clearing cache for specific symbol."""
        client = self.create_mock_schwab_client()
        fetcher = SchwabPriceDataFetcher(client)

        price_data = PriceData(dates=["2026-01-01"], closes=[100.0])
        fetcher.cache.set("AAPL", 60, price_data)
        fetcher.cache.set("TSLA", 60, price_data)

        fetcher.clear_cache("AAPL")

        assert fetcher.cache.get("AAPL", 60) is None
        assert fetcher.cache.get("TSLA", 60) is not None

    def test_symbol_normalization(self):
        """Test that symbols are normalized to uppercase."""
        client = self.create_mock_schwab_client()
        fetcher = SchwabPriceDataFetcher(client, enable_cache=False)

        mock_price_data = self.create_mock_price_data(20)
        client.get_price_history.return_value = mock_price_data

        fetcher.fetch_price_data("aapl", lookback_days=20)

        # Verify Schwab client was called with uppercase symbol
        call_kwargs = client.get_price_history.call_args[1]
        assert call_kwargs["symbol"] == "AAPL"
