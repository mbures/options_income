"""Unit tests for SQLite-based market data cache module."""

import json
import sqlite3
import pytest
from datetime import datetime, timedelta
from pathlib import Path

from src.cache import LocalFileCache, CacheError


class TestLocalFileCacheInit:
    """Test suite for LocalFileCache initialization."""

    def test_cache_creates_directory(self, tmp_path):
        """Test that cache creates directory if it doesn't exist."""
        cache_dir = tmp_path / "test_cache"
        assert not cache_dir.exists()

        cache = LocalFileCache(cache_dir=str(cache_dir))

        assert cache_dir.exists()
        assert cache_dir.is_dir()

    def test_cache_uses_existing_directory(self, tmp_path):
        """Test that cache uses existing directory."""
        cache_dir = tmp_path / "existing_cache"
        cache_dir.mkdir()
        (cache_dir / "existing_file.txt").write_text("test")

        cache = LocalFileCache(cache_dir=str(cache_dir))

        assert cache_dir.exists()
        assert (cache_dir / "existing_file.txt").exists()

    def test_cache_default_directory(self):
        """Test default cache directory is in project root."""
        cache = LocalFileCache()
        # Default should be 'cache' directory in project root
        assert cache.cache_dir.name == "cache"

    def test_cache_creates_database(self, tmp_path):
        """Test that cache creates SQLite database."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        db_path = tmp_path / "cache.db"
        assert db_path.exists()

    def test_cache_creates_tables(self, tmp_path):
        """Test that cache creates required tables."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        # Check tables exist
        conn = sqlite3.connect(str(tmp_path / "cache.db"))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "market_data" in tables
        assert "api_usage" in tables


class TestLocalFileCacheStockPrices:
    """Test suite for stock price market data methods."""

    def test_set_and_get_stock_price(self, tmp_path):
        """Test setting and getting a single stock price."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        data = {
            "open": 150.0,
            "high": 152.0,
            "low": 149.0,
            "close": 151.5,
            "volume": 1000000
        }
        cache.set_stock_price("AAPL", "2026-01-15", data)

        result = cache.get_stock_prices("AAPL")
        assert "2026-01-15" in result
        assert result["2026-01-15"]["close"] == 151.5

    def test_set_stock_prices_multiple(self, tmp_path):
        """Test setting multiple stock prices at once."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        prices = {
            "2026-01-13": {"open": 149.0, "high": 150.0, "low": 148.0, "close": 149.5, "volume": 900000},
            "2026-01-14": {"open": 149.5, "high": 151.0, "low": 149.0, "close": 150.5, "volume": 1000000},
            "2026-01-15": {"open": 150.5, "high": 152.0, "low": 150.0, "close": 151.5, "volume": 1100000}
        }

        count = cache.set_stock_prices("AAPL", prices)

        assert count == 3
        result = cache.get_stock_prices("AAPL")
        assert len(result) == 3

    def test_get_stock_prices_date_filter(self, tmp_path):
        """Test filtering stock prices by date range."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        prices = {
            "2026-01-10": {"close": 148.0},
            "2026-01-11": {"close": 149.0},
            "2026-01-12": {"close": 150.0},
            "2026-01-13": {"close": 151.0},
            "2026-01-14": {"close": 152.0}
        }
        cache.set_stock_prices("AAPL", prices)

        # Filter by date range
        result = cache.get_stock_prices("AAPL", start_date="2026-01-11", end_date="2026-01-13")
        assert len(result) == 3
        assert "2026-01-10" not in result
        assert "2026-01-14" not in result

    def test_get_stock_prices_max_age(self, tmp_path):
        """Test max_age_hours filter for stock prices."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        cache.set_stock_price("AAPL", "2026-01-15", {"close": 150.0})

        # Make the entry old
        old_time = (datetime.now() - timedelta(hours=48)).isoformat()
        conn = sqlite3.connect(str(tmp_path / "cache.db"))
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE market_data SET cached_at = ? WHERE symbol = ?",
            (old_time, "AAPL")
        )
        conn.commit()
        conn.close()

        # Without max_age_hours, should return data
        result = cache.get_stock_prices("AAPL")
        assert len(result) == 1

        # With max_age_hours, should return empty
        result = cache.get_stock_prices("AAPL", max_age_hours=24.0)
        assert len(result) == 0

    def test_stock_price_symbol_normalization(self, tmp_path):
        """Test that symbols are normalized to uppercase."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        cache.set_stock_price("aapl", "2026-01-15", {"close": 150.0})

        # Should be able to retrieve with uppercase
        result = cache.get_stock_prices("AAPL")
        assert len(result) == 1

    def test_stock_price_overwrites_existing(self, tmp_path):
        """Test that setting same stock price overwrites existing."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        cache.set_stock_price("AAPL", "2026-01-15", {"close": 150.0})
        cache.set_stock_price("AAPL", "2026-01-15", {"close": 155.0})

        result = cache.get_stock_prices("AAPL")
        assert result["2026-01-15"]["close"] == 155.0

    def test_has_stock_prices(self, tmp_path):
        """Test checking for cached stock prices."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        assert cache.has_stock_prices("AAPL") is False

        cache.set_stock_price("AAPL", "2026-01-15", {"close": 150.0})

        assert cache.has_stock_prices("AAPL") is True
        assert cache.has_stock_prices("GOOG") is False

    def test_has_stock_prices_with_max_age(self, tmp_path):
        """Test has_stock_prices with max_age_hours."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        cache.set_stock_price("AAPL", "2026-01-15", {"close": 150.0})

        # Make the entry old
        old_time = (datetime.now() - timedelta(hours=48)).isoformat()
        conn = sqlite3.connect(str(tmp_path / "cache.db"))
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE market_data SET cached_at = ? WHERE symbol = ?",
            (old_time, "AAPL")
        )
        conn.commit()
        conn.close()

        # Without max_age, should return True
        assert cache.has_stock_prices("AAPL") is True

        # With max_age, should return False (data is too old)
        assert cache.has_stock_prices("AAPL", max_age_hours=24.0) is False


class TestLocalFileCacheOptionContracts:
    """Test suite for option contract market data methods."""

    def test_set_and_get_option_contract(self, tmp_path):
        """Test setting and getting a single option contract."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        contract = {
            "expiration_date": "2026-02-21",
            "strike": 150.0,
            "option_type": "Call",
            "bid": 5.50,
            "ask": 5.75,
            "last": 5.60,
            "volume": 500,
            "open_interest": 2000,
            "implied_volatility": 0.25
        }
        cache.set_option_contract("AAPL", "2026-01-15T10:00:00", contract)

        result = cache.get_option_contracts("AAPL")
        assert len(result) == 1
        assert result[0]["strike"] == 150.0
        assert result[0]["option_type"] == "Call"

    def test_set_option_contracts_multiple(self, tmp_path):
        """Test setting multiple option contracts at once."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        contracts = [
            {"expiration_date": "2026-02-21", "strike": 145.0, "option_type": "Call", "bid": 8.0},
            {"expiration_date": "2026-02-21", "strike": 150.0, "option_type": "Call", "bid": 5.5},
            {"expiration_date": "2026-02-21", "strike": 155.0, "option_type": "Call", "bid": 3.0},
            {"expiration_date": "2026-02-21", "strike": 150.0, "option_type": "Put", "bid": 4.5}
        ]

        count = cache.set_option_contracts("AAPL", "2026-01-15T10:00:00", contracts)

        assert count == 4
        result = cache.get_option_contracts("AAPL")
        assert len(result) == 4

    def test_get_option_contracts_by_expiration(self, tmp_path):
        """Test filtering options by expiration date."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        contracts = [
            {"expiration_date": "2026-02-21", "strike": 150.0, "option_type": "Call"},
            {"expiration_date": "2026-03-21", "strike": 150.0, "option_type": "Call"},
            {"expiration_date": "2026-02-21", "strike": 155.0, "option_type": "Call"}
        ]
        cache.set_option_contracts("AAPL", "2026-01-15T10:00:00", contracts)

        result = cache.get_option_contracts("AAPL", expiration_date="2026-02-21")
        assert len(result) == 2

    def test_get_option_contracts_by_strike(self, tmp_path):
        """Test filtering options by strike price."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        contracts = [
            {"expiration_date": "2026-02-21", "strike": 150.0, "option_type": "Call"},
            {"expiration_date": "2026-02-21", "strike": 150.0, "option_type": "Put"},
            {"expiration_date": "2026-02-21", "strike": 155.0, "option_type": "Call"}
        ]
        cache.set_option_contracts("AAPL", "2026-01-15T10:00:00", contracts)

        result = cache.get_option_contracts("AAPL", strike=150.0)
        assert len(result) == 2

    def test_get_option_contracts_by_type(self, tmp_path):
        """Test filtering options by option type."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        contracts = [
            {"expiration_date": "2026-02-21", "strike": 150.0, "option_type": "Call"},
            {"expiration_date": "2026-02-21", "strike": 150.0, "option_type": "Put"},
            {"expiration_date": "2026-02-21", "strike": 155.0, "option_type": "Put"}
        ]
        cache.set_option_contracts("AAPL", "2026-01-15T10:00:00", contracts)

        result = cache.get_option_contracts("AAPL", option_type="Put")
        assert len(result) == 2

    def test_option_contract_missing_required_fields(self, tmp_path):
        """Test that contracts missing required fields raise ValueError."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        contract = {"bid": 5.50}  # Missing expiration_date, strike, option_type

        with pytest.raises(ValueError, match="Missing required contract fields"):
            cache.set_option_contract("AAPL", "2026-01-15T10:00:00", contract)

    def test_set_option_contracts_skips_invalid(self, tmp_path):
        """Test that invalid contracts are skipped when setting multiple."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        contracts = [
            {"expiration_date": "2026-02-21", "strike": 150.0, "option_type": "Call"},  # Valid
            {"bid": 5.50},  # Invalid - missing required fields
            {"expiration_date": "2026-02-21", "strike": 155.0, "option_type": "Call"}   # Valid
        ]

        count = cache.set_option_contracts("AAPL", "2026-01-15T10:00:00", contracts)

        assert count == 2  # Only 2 valid contracts
        result = cache.get_option_contracts("AAPL")
        assert len(result) == 2


class TestLocalFileCacheAPIUsageTracking:
    """Test suite for Alpha Vantage API usage tracking."""

    def test_get_usage_today_empty(self, tmp_path):
        """Test getting usage when no calls have been made."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        usage = cache.get_alpha_vantage_usage_today()

        assert usage == 0

    def test_increment_usage(self, tmp_path):
        """Test incrementing usage counter."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        count1 = cache.increment_alpha_vantage_usage()
        count2 = cache.increment_alpha_vantage_usage()
        count3 = cache.increment_alpha_vantage_usage()

        assert count1 == 1
        assert count2 == 2
        assert count3 == 3

    def test_get_usage_after_increment(self, tmp_path):
        """Test getting usage after incrementing."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        cache.increment_alpha_vantage_usage()
        cache.increment_alpha_vantage_usage()
        usage = cache.get_alpha_vantage_usage_today()

        assert usage == 2

    def test_usage_persists_across_instances(self, tmp_path):
        """Test that usage tracking persists across cache instances."""
        cache1 = LocalFileCache(cache_dir=str(tmp_path))
        cache1.increment_alpha_vantage_usage()
        cache1.increment_alpha_vantage_usage()

        # Create new instance with same directory
        cache2 = LocalFileCache(cache_dir=str(tmp_path))
        usage = cache2.get_alpha_vantage_usage_today()

        assert usage == 2

    def test_usage_tracks_by_date(self, tmp_path):
        """Test that usage is tracked separately by date."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        # Set up usage for today
        cache.increment_alpha_vantage_usage()

        # Manually add usage for yesterday
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        conn = sqlite3.connect(str(tmp_path / "cache.db"))
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO api_usage (service, date, count) VALUES (?, ?, ?)",
            ("alpha_vantage", yesterday, 10)
        )
        conn.commit()
        conn.close()

        # Today's usage should still be 1
        assert cache.get_alpha_vantage_usage_today() == 1


class TestLocalFileCacheMarketData:
    """Test suite for general market data operations."""

    def test_delete_market_data_by_symbol(self, tmp_path):
        """Test deleting market data by symbol."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        cache.set_stock_price("AAPL", "2026-01-15", {"close": 150.0})
        cache.set_stock_price("GOOG", "2026-01-15", {"close": 100.0})

        count = cache.delete_market_data(symbol="AAPL")

        assert count == 1
        assert len(cache.get_stock_prices("AAPL")) == 0
        assert len(cache.get_stock_prices("GOOG")) == 1

    def test_delete_market_data_by_type(self, tmp_path):
        """Test deleting market data by type."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        cache.set_stock_price("AAPL", "2026-01-15", {"close": 150.0})
        cache.set_option_contract("AAPL", "2026-01-15T10:00:00", {
            "expiration_date": "2026-02-21",
            "strike": 150.0,
            "option_type": "Call"
        })

        count = cache.delete_market_data(data_type="stock")

        assert count == 1
        assert len(cache.get_stock_prices("AAPL")) == 0
        assert len(cache.get_option_contracts("AAPL")) == 1

    def test_delete_market_data_before_date(self, tmp_path):
        """Test deleting market data before a specific date."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        prices = {
            "2026-01-10": {"close": 148.0},
            "2026-01-11": {"close": 149.0},
            "2026-01-15": {"close": 152.0}
        }
        cache.set_stock_prices("AAPL", prices)

        count = cache.delete_market_data(before_date="2026-01-12")

        assert count == 2
        result = cache.get_stock_prices("AAPL")
        assert len(result) == 1
        assert "2026-01-15" in result

    def test_clear_all(self, tmp_path):
        """Test clearing all market data."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        cache.set_stock_price("AAPL", "2026-01-15", {"close": 150.0})
        cache.set_stock_price("GOOG", "2026-01-15", {"close": 100.0})

        count = cache.clear_all()

        assert count == 2
        assert len(cache.get_stock_prices("AAPL")) == 0
        assert len(cache.get_stock_prices("GOOG")) == 0

    def test_clear_all_preserves_usage_tracking(self, tmp_path):
        """Test that clear_all preserves the API usage tracking."""
        cache = LocalFileCache(cache_dir=str(tmp_path))
        cache.set_stock_price("AAPL", "2026-01-15", {"close": 150.0})

        # Add some usage tracking
        cache.increment_alpha_vantage_usage()
        cache.increment_alpha_vantage_usage()

        cache.clear_all()

        # Usage should still be tracked
        assert cache.get_alpha_vantage_usage_today() == 2

    def test_get_stats(self, tmp_path):
        """Test getting cache statistics."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        # Add stock prices
        cache.set_stock_prices("AAPL", {
            "2026-01-14": {"close": 149.0},
            "2026-01-15": {"close": 150.0}
        })
        cache.set_stock_price("GOOG", "2026-01-15", {"close": 100.0})

        # Add options
        cache.set_option_contracts("AAPL", "2026-01-15T10:00:00", [
            {"expiration_date": "2026-02-21", "strike": 150.0, "option_type": "Call"},
            {"expiration_date": "2026-02-21", "strike": 150.0, "option_type": "Put"}
        ])

        stats = cache.get_stats()

        assert stats["stock_prices_count"] == 3
        assert stats["option_contracts_count"] == 2
        assert stats["total_entries"] == 5
        assert stats["unique_symbols"] == 2
        assert stats["oldest_data"] is not None
        assert stats["newest_data"] is not None
        assert stats["database_size_bytes"] > 0

    def test_cleanup_expired(self, tmp_path):
        """Test cleanup of expired market data."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        cache.set_stock_price("AAPL", "2026-01-15", {"close": 150.0})
        cache.set_stock_price("AAPL", "2026-01-14", {"close": 149.0})

        # Make one entry old
        old_time = (datetime.now() - timedelta(hours=48)).isoformat()
        conn = sqlite3.connect(str(tmp_path / "cache.db"))
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE market_data SET cached_at = ? WHERE timestamp = ?",
            (old_time, "2026-01-14")
        )
        conn.commit()
        conn.close()

        count = cache.cleanup_expired(max_age_hours=24.0)

        assert count == 1
        result = cache.get_stock_prices("AAPL")
        assert len(result) == 1
        assert "2026-01-15" in result

    def test_stock_and_option_data_coexist(self, tmp_path):
        """Test that stock and option data can coexist for same symbol."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        # Add both stock and option data
        cache.set_stock_price("AAPL", "2026-01-15", {"close": 150.0})
        cache.set_option_contract("AAPL", "2026-01-15T10:00:00", {
            "expiration_date": "2026-02-21",
            "strike": 150.0,
            "option_type": "Call"
        })

        # Both should be retrievable independently
        stock_result = cache.get_stock_prices("AAPL")
        option_result = cache.get_option_contracts("AAPL")

        assert len(stock_result) == 1
        assert len(option_result) == 1


class TestLocalFileCacheIntegration:
    """Integration tests for cache operations."""

    def test_price_data_caching_workflow(self, tmp_path):
        """Test typical price data caching workflow."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        # Simulate caching price data
        prices = {
            "2026-01-13": {"open": 149.5, "high": 152.0, "low": 148.0, "close": 150.0, "volume": 1000000},
            "2026-01-14": {"open": 150.5, "high": 153.0, "low": 149.0, "close": 151.5, "volume": 1100000},
            "2026-01-15": {"open": 151.0, "high": 154.0, "low": 150.0, "close": 152.0, "volume": 1200000}
        }

        cache.set_stock_prices("AAPL", prices)

        # Check API usage
        cache.increment_alpha_vantage_usage()

        # Retrieve and verify
        cached = cache.get_stock_prices("AAPL")
        assert len(cached) == 3
        assert cached["2026-01-15"]["close"] == 152.0

        # Check usage
        assert cache.get_alpha_vantage_usage_today() == 1

    def test_concurrent_access(self, tmp_path):
        """Test that multiple cache instances can access the same database."""
        cache1 = LocalFileCache(cache_dir=str(tmp_path))
        cache2 = LocalFileCache(cache_dir=str(tmp_path))

        # Write from one instance
        cache1.set_stock_price("AAPL", "2026-01-15", {"close": 150.0})

        # Read from another
        result = cache2.get_stock_prices("AAPL")
        assert len(result) == 1
        assert result["2026-01-15"]["close"] == 150.0

        # Increment usage from both
        cache1.increment_alpha_vantage_usage()
        cache2.increment_alpha_vantage_usage()

        # Both should see the total
        assert cache1.get_alpha_vantage_usage_today() == 2
        assert cache2.get_alpha_vantage_usage_today() == 2
