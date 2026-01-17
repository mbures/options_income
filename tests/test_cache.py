"""Unit tests for local file cache module."""

import json
import os
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

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


class TestLocalFileCacheKeyManagement:
    """Test suite for cache key sanitization."""

    def test_key_sanitization_alphanumeric(self, tmp_path):
        """Test that alphanumeric keys are preserved."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        path = cache._get_cache_path("AAPL_daily_2026")
        assert "AAPL_daily_2026" in str(path)

    def test_key_sanitization_special_characters(self, tmp_path):
        """Test that special characters are sanitized."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        # Keys with special characters should be sanitized
        path = cache._get_cache_path("test/key:with*special?chars")
        # Should not contain filesystem-unsafe characters
        assert "/" not in path.name
        assert ":" not in path.name
        assert "*" not in path.name
        assert "?" not in path.name

    def test_key_generates_json_file(self, tmp_path):
        """Test that cache paths end with .json extension."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        path = cache._get_cache_path("test_key")
        assert path.suffix == ".json"


class TestLocalFileCacheSetGet:
    """Test suite for cache set and get operations."""

    def test_set_and_get_basic(self, tmp_path):
        """Test basic set and get operations."""
        cache = LocalFileCache(cache_dir=str(tmp_path))
        data = {"symbol": "AAPL", "price": 150.25}

        cache.set("test_key", data)
        result = cache.get("test_key")

        assert result is not None
        assert result["symbol"] == "AAPL"
        assert result["price"] == 150.25

    def test_set_adds_timestamp(self, tmp_path):
        """Test that set adds _cached_at timestamp."""
        cache = LocalFileCache(cache_dir=str(tmp_path))
        data = {"value": 42}

        cache.set("test_key", data)
        result = cache.get("test_key")

        assert "_cached_at" in result
        # Should be a valid ISO timestamp
        datetime.fromisoformat(result["_cached_at"])

    def test_get_nonexistent_key(self, tmp_path):
        """Test that get returns None for nonexistent keys."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        result = cache.get("nonexistent_key")

        assert result is None

    def test_set_overwrites_existing(self, tmp_path):
        """Test that set overwrites existing data."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        cache.set("key", {"version": 1})
        cache.set("key", {"version": 2})
        result = cache.get("key")

        assert result["version"] == 2

    def test_get_with_ttl_valid(self, tmp_path):
        """Test get with TTL returns data if within TTL."""
        cache = LocalFileCache(cache_dir=str(tmp_path))
        data = {"value": "fresh"}

        cache.set("key", data)
        result = cache.get("key", max_age_hours=1.0)

        assert result is not None
        assert result["value"] == "fresh"

    def test_get_with_ttl_expired(self, tmp_path):
        """Test get with TTL returns None if data is expired."""
        cache = LocalFileCache(cache_dir=str(tmp_path))
        data = {"value": "stale"}

        # Set data with old timestamp
        cache.set("key", data)
        # Manually update the timestamp to be old
        cache_path = cache._get_cache_path("key")
        with open(cache_path, "r") as f:
            cached_data = json.load(f)
        old_time = (datetime.now() - timedelta(hours=2)).isoformat()
        cached_data["_cached_at"] = old_time
        with open(cache_path, "w") as f:
            json.dump(cached_data, f)

        result = cache.get("key", max_age_hours=1.0)

        assert result is None

    def test_get_without_ttl_ignores_age(self, tmp_path):
        """Test get without TTL returns data regardless of age."""
        cache = LocalFileCache(cache_dir=str(tmp_path))
        data = {"value": "old_data"}

        cache.set("key", data)
        # Manually set old timestamp
        cache_path = cache._get_cache_path("key")
        with open(cache_path, "r") as f:
            cached_data = json.load(f)
        old_time = (datetime.now() - timedelta(days=30)).isoformat()
        cached_data["_cached_at"] = old_time
        with open(cache_path, "w") as f:
            json.dump(cached_data, f)

        result = cache.get("key")  # No max_age_hours

        assert result is not None
        assert result["value"] == "old_data"

    def test_set_complex_data(self, tmp_path):
        """Test setting complex nested data structures."""
        cache = LocalFileCache(cache_dir=str(tmp_path))
        data = {
            "symbol": "AAPL",
            "prices": [150.0, 151.5, 149.0],
            "metadata": {
                "source": "alpha_vantage",
                "nested": {"deep": True}
            }
        }

        cache.set("complex", data)
        result = cache.get("complex")

        assert result["prices"] == [150.0, 151.5, 149.0]
        assert result["metadata"]["nested"]["deep"] is True


class TestLocalFileCacheDelete:
    """Test suite for cache delete operations."""

    def test_delete_existing_key(self, tmp_path):
        """Test deleting an existing cache entry."""
        cache = LocalFileCache(cache_dir=str(tmp_path))
        cache.set("to_delete", {"data": 1})

        result = cache.delete("to_delete")

        assert result is True
        assert cache.get("to_delete") is None

    def test_delete_nonexistent_key(self, tmp_path):
        """Test deleting a nonexistent key returns False."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        result = cache.delete("nonexistent")

        assert result is False

    def test_clear_all(self, tmp_path):
        """Test clearing all cache entries."""
        cache = LocalFileCache(cache_dir=str(tmp_path))
        cache.set("key1", {"data": 1})
        cache.set("key2", {"data": 2})
        cache.set("key3", {"data": 3})

        count = cache.clear_all()

        assert count == 3
        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert cache.get("key3") is None

    def test_clear_all_preserves_usage_file(self, tmp_path):
        """Test that clear_all preserves the API usage tracking file."""
        cache = LocalFileCache(cache_dir=str(tmp_path))
        cache.set("key1", {"data": 1})
        # Create a usage file
        usage_file = tmp_path / "api_usage.json"
        usage_file.write_text('{"alpha_vantage": {"2026-01-15": 5}}')

        cache.clear_all()

        assert usage_file.exists()

    def test_clear_all_empty_cache(self, tmp_path):
        """Test clearing an empty cache."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        count = cache.clear_all()

        assert count == 0


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
        usage_file = tmp_path / "api_usage.json"
        with open(usage_file, "r") as f:
            usage_data = json.load(f)
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        usage_data["alpha_vantage"][yesterday] = 10
        with open(usage_file, "w") as f:
            json.dump(usage_data, f)

        # Today's usage should still be 1
        assert cache.get_alpha_vantage_usage_today() == 1


class TestLocalFileCacheErrorHandling:
    """Test suite for error handling."""

    def test_get_handles_corrupted_json(self, tmp_path):
        """Test that get handles corrupted JSON gracefully."""
        cache = LocalFileCache(cache_dir=str(tmp_path))
        cache_path = cache._get_cache_path("corrupted")
        cache_path.write_text("not valid json {{{")

        result = cache.get("corrupted")

        assert result is None

    def test_get_handles_missing_timestamp(self, tmp_path):
        """Test that get handles data without timestamp."""
        cache = LocalFileCache(cache_dir=str(tmp_path))
        cache_path = cache._get_cache_path("no_timestamp")
        cache_path.write_text('{"data": "value"}')

        # Without max_age_hours, should return data
        result = cache.get("no_timestamp")
        assert result is not None

        # With max_age_hours, should return None (can't validate age)
        result = cache.get("no_timestamp", max_age_hours=1.0)
        assert result is None


class TestLocalFileCacheIntegration:
    """Integration tests for cache operations."""

    def test_price_data_caching_workflow(self, tmp_path):
        """Test typical price data caching workflow."""
        cache = LocalFileCache(cache_dir=str(tmp_path))

        # Simulate caching price data
        price_data = {
            "symbol": "AAPL",
            "dates": ["2026-01-13", "2026-01-14", "2026-01-15"],
            "closes": [150.0, 151.5, 152.0],
            "opens": [149.5, 150.5, 151.0],
            "highs": [152.0, 153.0, 154.0],
            "lows": [148.0, 149.0, 150.0],
            "volumes": [1000000, 1100000, 1200000]
        }

        cache_key = f"price_daily_AAPL_compact"
        cache.set(cache_key, price_data)

        # Check API usage
        cache.increment_alpha_vantage_usage()

        # Retrieve and verify
        cached = cache.get(cache_key, max_age_hours=24)
        assert cached is not None
        assert cached["symbol"] == "AAPL"
        assert len(cached["closes"]) == 3

        # Check usage
        assert cache.get_alpha_vantage_usage_today() == 1
