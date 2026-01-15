"""Unit tests for price data fetcher module."""

import pytest
import time
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from src.price_fetcher import (
    PriceDataFetcher,
    PriceDataCache,
    CacheEntry
)
from src.volatility import PriceData
from src.finnhub_client import FinnhubAPIError


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
    """Test suite for PriceDataFetcher class."""

    def create_mock_client(self):
        """Create a mock FinnhubClient."""
        client = Mock()
        client.config = Mock()
        client.config.base_url = "https://finnhub.io/api/v1"
        client.config.api_key = "test_key"
        client.config.timeout = 10
        client.session = Mock()
        return client

    def create_mock_candle_response(self, n_days=60):
        """Create a mock successful candle response."""
        base_time = int(datetime(2026, 1, 1).timestamp())
        day_seconds = 86400

        return {
            "s": "ok",
            "t": [base_time + i * day_seconds for i in range(n_days)],
            "o": [100.0 + i * 0.1 for i in range(n_days)],
            "h": [102.0 + i * 0.1 for i in range(n_days)],
            "l": [99.0 + i * 0.1 for i in range(n_days)],
            "c": [101.0 + i * 0.1 for i in range(n_days)],
            "v": [1000000 + i * 1000 for i in range(n_days)]
        }

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

        # Mock API response
        mock_response = Mock()
        mock_response.json.return_value = self.create_mock_candle_response(60)
        mock_response.raise_for_status = Mock()
        client.session.get.return_value = mock_response

        # Fetch data
        price_data = fetcher.fetch_price_data("F", lookback_days=60)

        assert isinstance(price_data, PriceData)
        assert len(price_data.dates) == 60
        assert len(price_data.closes) == 60
        assert len(price_data.opens) == 60
        assert len(price_data.highs) == 60
        assert len(price_data.lows) == 60
        assert price_data.volumes is not None

    def test_fetch_price_data_uses_cache(self):
        """Test that fetcher uses cached data."""
        client = self.create_mock_client()
        fetcher = PriceDataFetcher(client, enable_cache=True)

        # Mock first API call
        mock_response = Mock()
        mock_response.json.return_value = self.create_mock_candle_response(60)
        mock_response.raise_for_status = Mock()
        client.session.get.return_value = mock_response

        # First fetch - should hit API
        price_data_1 = fetcher.fetch_price_data("F", lookback_days=60)
        assert client.session.get.call_count == 1

        # Second fetch - should use cache
        price_data_2 = fetcher.fetch_price_data("F", lookback_days=60)
        assert client.session.get.call_count == 1  # Still 1, no new call

        # Data should be identical
        assert price_data_1.dates == price_data_2.dates

    def test_fetch_price_data_no_data(self):
        """Test handling of no data response."""
        client = self.create_mock_client()
        fetcher = PriceDataFetcher(client, enable_cache=False)

        # Mock no data response
        mock_response = Mock()
        mock_response.json.return_value = {"s": "no_data"}
        mock_response.raise_for_status = Mock()
        client.session.get.return_value = mock_response

        with pytest.raises(ValueError, match="No price data available"):
            fetcher.fetch_price_data("INVALID")

    def test_fetch_price_data_api_error(self):
        """Test handling of API errors."""
        client = self.create_mock_client()
        fetcher = PriceDataFetcher(client, enable_cache=False)

        # Mock API error
        client.session.get.side_effect = Exception("API Error")

        with pytest.raises(FinnhubAPIError, match="Failed to fetch candle data"):
            fetcher.fetch_price_data("F")

    def test_parse_candle_response(self):
        """Test parsing of candle response."""
        client = self.create_mock_client()
        fetcher = PriceDataFetcher(client)

        response = self.create_mock_candle_response(30)

        price_data = fetcher._parse_candle_response(response, "F", 30)

        assert len(price_data.dates) == 30
        assert len(price_data.closes) == 30
        assert all(isinstance(d, str) for d in price_data.dates)
        assert all(isinstance(c, float) for c in price_data.closes)

    def test_parse_candle_response_filters_to_window(self):
        """Test that parser filters to requested window."""
        client = self.create_mock_client()
        fetcher = PriceDataFetcher(client)

        # Response has 60 days, but we only want 20
        response = self.create_mock_candle_response(60)

        price_data = fetcher._parse_candle_response(response, "F", 20)

        assert len(price_data.dates) == 20

    def test_validate_price_data_success(self):
        """Test price data validation with valid data."""
        client = self.create_mock_client()
        fetcher = PriceDataFetcher(client)

        opens = [100.0, 101.0, 102.0]
        highs = [102.0, 103.0, 104.0]
        lows = [99.0, 100.0, 101.0]
        closes = [101.0, 102.0, 103.0]

        # Should not raise
        fetcher._validate_price_data(opens, highs, lows, closes)

    def test_validate_price_data_non_positive(self):
        """Test validation catches non-positive prices."""
        client = self.create_mock_client()
        fetcher = PriceDataFetcher(client)

        opens = [100.0, 0.0]  # Invalid
        highs = [102.0, 102.0]
        lows = [99.0, 99.0]
        closes = [101.0, 101.0]

        with pytest.raises(ValueError, match="Non-positive price"):
            fetcher._validate_price_data(opens, highs, lows, closes)

    def test_validate_price_data_high_less_than_low(self):
        """Test validation catches high < low."""
        client = self.create_mock_client()
        fetcher = PriceDataFetcher(client)

        opens = [100.0, 101.0]
        highs = [102.0, 99.0]  # High < Low
        lows = [99.0, 100.0]
        closes = [101.0, 100.5]

        with pytest.raises(ValueError, match="High < Low"):
            fetcher._validate_price_data(opens, highs, lows, closes)

    def test_fetch_multiple_windows(self):
        """Test fetching multiple lookback windows."""
        client = self.create_mock_client()
        fetcher = PriceDataFetcher(client, enable_cache=False)

        # Mock API response
        mock_response = Mock()
        mock_response.json.return_value = self.create_mock_candle_response(252)
        mock_response.raise_for_status = Mock()
        client.session.get.return_value = mock_response

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

        mock_response = Mock()
        mock_response.json.return_value = self.create_mock_candle_response(20)
        mock_response.raise_for_status = Mock()
        client.session.get.return_value = mock_response

        # Fetch with lowercase symbol
        price_data = fetcher.fetch_price_data("aapl", lookback_days=20)

        # Verify API was called with uppercase
        call_args = client.session.get.call_args
        assert call_args[1]["params"]["symbol"] == "AAPL"
