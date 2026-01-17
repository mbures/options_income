"""Local file-based cache for API data with TTL support and usage tracking."""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class CacheError(Exception):
    """Exception raised for cache-related errors."""

    pass


class LocalFileCache:
    """
    File-based cache for storing API responses locally.

    Features:
    - JSON-based storage for human readability
    - TTL (time-to-live) validation on read
    - API usage tracking (especially for Alpha Vantage daily limits)
    - Safe key sanitization for filesystem compatibility

    Attributes:
        cache_dir: Directory where cache files are stored
    """

    def __init__(self, cache_dir: Optional[str] = None):
        """
        Initialize the cache.

        Args:
            cache_dir: Directory for cache files. Defaults to 'cache/' in project root.
        """
        if cache_dir is None:
            # Default to 'cache' directory in project root
            project_root = Path(__file__).parent.parent
            self.cache_dir = project_root / "cache"
        else:
            self.cache_dir = Path(cache_dir)

        # Create cache directory if it doesn't exist
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Usage tracking file
        self._usage_file = self.cache_dir / "api_usage.json"

        logging.debug(f"LocalFileCache initialized at {self.cache_dir}")

    def _get_cache_path(self, key: str) -> Path:
        """
        Get the filesystem path for a cache key.

        Args:
            key: Cache key to convert to path

        Returns:
            Path object for the cache file
        """
        # Sanitize key for filesystem safety
        # Replace any non-alphanumeric characters (except underscore and hyphen) with underscore
        safe_key = re.sub(r"[^a-zA-Z0-9_-]", "_", key)
        return self.cache_dir / f"{safe_key}.json"

    def get(
        self, key: str, max_age_hours: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve data from cache.

        Args:
            key: Cache key to retrieve
            max_age_hours: Maximum age in hours for the cached data.
                          If None, returns data regardless of age.
                          If specified, returns None if data is older than this.

        Returns:
            Cached data as dictionary, or None if not found/expired/invalid
        """
        cache_path = self._get_cache_path(key)

        if not cache_path.exists():
            logging.debug(f"Cache miss: {key}")
            return None

        try:
            with open(cache_path, "r") as f:
                data = json.load(f)

            # Check expiry if max_age_hours is specified
            if max_age_hours is not None:
                cached_at_str = data.get("_cached_at")
                if cached_at_str is None:
                    logging.debug(f"Cache entry has no timestamp: {key}")
                    return None

                try:
                    cached_at = datetime.fromisoformat(cached_at_str)
                    age_hours = (datetime.now() - cached_at).total_seconds() / 3600
                    if age_hours > max_age_hours:
                        logging.debug(
                            f"Cache expired: {key} (age: {age_hours:.1f}h > {max_age_hours}h)"
                        )
                        return None
                except ValueError:
                    logging.warning(f"Invalid timestamp in cache: {key}")
                    return None

            logging.debug(f"Cache hit: {key}")
            return data

        except json.JSONDecodeError as e:
            logging.warning(f"Cache read error (invalid JSON) for {key}: {e}")
            return None
        except IOError as e:
            logging.warning(f"Cache read error (IO) for {key}: {e}")
            return None

    def set(self, key: str, data: Dict[str, Any]) -> None:
        """
        Store data in cache.

        Args:
            key: Cache key
            data: Data to cache (must be JSON serializable)

        Raises:
            CacheError: If data cannot be written to cache
        """
        cache_path = self._get_cache_path(key)

        # Add timestamp
        data_with_timestamp = data.copy()
        data_with_timestamp["_cached_at"] = datetime.now().isoformat()

        try:
            with open(cache_path, "w") as f:
                json.dump(data_with_timestamp, f, indent=2)
            logging.debug(f"Cached: {key}")
        except (IOError, TypeError) as e:
            logging.error(f"Cache write error for {key}: {e}")
            raise CacheError(f"Failed to write cache for {key}: {e}")

    def delete(self, key: str) -> bool:
        """
        Delete a cache entry.

        Args:
            key: Cache key to delete

        Returns:
            True if entry was deleted, False if it didn't exist
        """
        cache_path = self._get_cache_path(key)
        if cache_path.exists():
            cache_path.unlink()
            logging.debug(f"Deleted cache: {key}")
            return True
        return False

    def clear_all(self) -> int:
        """
        Clear all cache entries except API usage tracking.

        Returns:
            Number of cache entries deleted
        """
        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            # Preserve the API usage tracking file
            if cache_file.name != "api_usage.json":
                cache_file.unlink()
                count += 1
        logging.info(f"Cleared {count} cache entries")
        return count

    # ==================== API Usage Tracking ====================

    def get_alpha_vantage_usage_today(self) -> int:
        """
        Get number of Alpha Vantage API calls made today.

        Returns:
            Number of API calls made today
        """
        usage = self._load_usage()
        today = datetime.now().strftime("%Y-%m-%d")
        return usage.get("alpha_vantage", {}).get(today, 0)

    def increment_alpha_vantage_usage(self) -> int:
        """
        Increment and return today's Alpha Vantage usage count.

        Returns:
            Updated usage count for today
        """
        usage = self._load_usage()
        today = datetime.now().strftime("%Y-%m-%d")

        if "alpha_vantage" not in usage:
            usage["alpha_vantage"] = {}

        usage["alpha_vantage"][today] = usage["alpha_vantage"].get(today, 0) + 1
        self._save_usage(usage)

        return usage["alpha_vantage"][today]

    def _load_usage(self) -> Dict[str, Any]:
        """
        Load API usage tracking data.

        Returns:
            Usage data dictionary
        """
        if self._usage_file.exists():
            try:
                with open(self._usage_file, "r") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logging.warning("Corrupted usage file, resetting")
                return {}
        return {}

    def _save_usage(self, usage: Dict[str, Any]) -> None:
        """
        Save API usage tracking data.

        Args:
            usage: Usage data to save
        """
        with open(self._usage_file, "w") as f:
            json.dump(usage, f, indent=2)
