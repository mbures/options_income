"""SQLite-based cache for market data with TTL support and usage tracking.

This module provides a persistent cache using SQLite for storing market data
(stock prices and option contracts) with proper schema and API usage tracking.

Features:
- SQLite-based storage for reliability and performance
- Unified market_data table for stocks and options
- TTL (time-to-live) validation on read
- API usage tracking (especially for Alpha Vantage daily limits)
- JSON column support with SQLite JSON1 extension
- Thread-safe operations

Schema:
    market_data:
        - timestamp: Data point timestamp (trading date for stocks, retrieval time for options)
        - symbol: Stock ticker symbol
        - data_type: 'stock' or 'option'
        - json_data: Full data as JSON
        - expiration_date: For options only (NULL for stocks)
        - strike: For options only (NULL for stocks)
        - option_type: 'Call' or 'Put' for options (NULL for stocks)
        - cached_at: When the data was cached

    api_usage:
        - service: API service name (e.g., 'alpha_vantage')
        - date: Date of usage
        - count: Number of API calls
"""

import json
import logging
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class CacheError(Exception):
    """Exception raised for cache-related errors."""

    pass


class LocalFileCache:
    """
    SQLite-based cache for storing market data locally.

    All market data (stock prices and option contracts) flows through a single
    unified table with proper schema for efficient querying.

    Features:
    - SQLite storage for reliability and atomic operations
    - Unified market_data table for stocks and options
    - TTL (time-to-live) validation on read
    - API usage tracking (especially for Alpha Vantage daily limits)
    - JSON column support for flexible data storage

    Attributes:
        cache_dir: Directory where the cache database is stored
        db_path: Path to the SQLite database file
    """

    DB_FILENAME = "cache.db"

    # Data type constants
    DATA_TYPE_STOCK = "stock"
    DATA_TYPE_OPTION = "option"

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

        # Database path
        self.db_path = self.cache_dir / self.DB_FILENAME

        # Initialize database schema
        self._init_db()

        logger.debug(f"LocalFileCache initialized at {self.cache_dir}")

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Get a database connection with proper cleanup.

        Yields:
            SQLite connection object
        """
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Create market_data table (unified schema for stocks and options)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS market_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    data_type TEXT NOT NULL,
                    json_data TEXT NOT NULL,
                    expiration_date TEXT,
                    strike REAL,
                    option_type TEXT,
                    cached_at TEXT NOT NULL,
                    UNIQUE(timestamp, symbol, data_type, expiration_date, strike, option_type)
                )
            """)

            # Create indexes for efficient queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_market_data_symbol_type
                ON market_data(symbol, data_type)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_market_data_timestamp
                ON market_data(timestamp)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_market_data_cached_at
                ON market_data(cached_at)
            """)

            # Create api_usage table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_usage (
                    service TEXT NOT NULL,
                    date TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (service, date)
                )
            """)

            conn.commit()
            logger.debug("Database schema initialized")

    # ==================== Stock Price Methods ====================

    def set_stock_price(self, symbol: str, timestamp: str, data: dict[str, Any]) -> None:
        """
        Store a single stock price data point.

        Args:
            symbol: Stock ticker symbol (e.g., "AAPL")
            timestamp: Trading date in ISO format (YYYY-MM-DD)
            data: OHLCV data dictionary with keys: open, high, low, close, volume

        Raises:
            CacheError: If data cannot be written
        """
        symbol = symbol.upper()
        cached_at = datetime.now().isoformat()

        try:
            json_data = json.dumps(data)

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO market_data
                    (timestamp, symbol, data_type, json_data, expiration_date, strike, option_type, cached_at)
                    VALUES (?, ?, ?, ?, NULL, NULL, NULL, ?)
                    """,
                    (timestamp, symbol, self.DATA_TYPE_STOCK, json_data, cached_at),
                )
                conn.commit()

            logger.debug(f"Cached stock price: {symbol} @ {timestamp}")

        except (sqlite3.Error, TypeError) as e:
            logger.error(f"Cache write error for stock {symbol}: {e}")
            raise CacheError(f"Failed to cache stock price for {symbol}: {e}") from e

    def set_stock_prices(self, symbol: str, prices: dict[str, dict[str, Any]]) -> int:
        """
        Store multiple stock price data points.

        Args:
            symbol: Stock ticker symbol
            prices: Dictionary mapping timestamps to OHLCV data
                    e.g., {"2026-01-15": {"open": 10.5, "high": 10.75, ...}}

        Returns:
            Number of price points stored

        Raises:
            CacheError: If data cannot be written
        """
        symbol = symbol.upper()
        cached_at = datetime.now().isoformat()
        count = 0

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                for timestamp, data in prices.items():
                    json_data = json.dumps(data)
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO market_data
                        (timestamp, symbol, data_type, json_data, expiration_date, strike, option_type, cached_at)
                        VALUES (?, ?, ?, ?, NULL, NULL, NULL, ?)
                        """,
                        (timestamp, symbol, self.DATA_TYPE_STOCK, json_data, cached_at),
                    )
                    count += 1

                conn.commit()

            logger.debug(f"Cached {count} stock prices for {symbol}")
            return count

        except (sqlite3.Error, TypeError) as e:
            logger.error(f"Cache write error for stock prices {symbol}: {e}")
            raise CacheError(f"Failed to cache stock prices for {symbol}: {e}") from e

    def get_stock_prices(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        max_age_hours: Optional[float] = None,
    ) -> dict[str, dict[str, Any]]:
        """
        Retrieve stock price data points.

        Args:
            symbol: Stock ticker symbol
            start_date: Optional start date filter (inclusive, YYYY-MM-DD)
            end_date: Optional end date filter (inclusive, YYYY-MM-DD)
            max_age_hours: Maximum cache age in hours (None = no limit)

        Returns:
            Dictionary mapping timestamps to OHLCV data
            e.g., {"2026-01-15": {"open": 10.5, "high": 10.75, ...}}
        """
        symbol = symbol.upper()
        result = {}

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Build query with optional filters
            query = """
                SELECT timestamp, json_data, cached_at
                FROM market_data
                WHERE symbol = ? AND data_type = ?
            """
            params: list[Any] = [symbol, self.DATA_TYPE_STOCK]

            if start_date:
                query += " AND timestamp >= ?"
                params.append(start_date)

            if end_date:
                query += " AND timestamp <= ?"
                params.append(end_date)

            if max_age_hours is not None:
                cutoff = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()
                query += " AND cached_at >= ?"
                params.append(cutoff)

            query += " ORDER BY timestamp"

            cursor.execute(query, params)
            rows = cursor.fetchall()

        for row in rows:
            try:
                data = json.loads(row["json_data"])
                result[row["timestamp"]] = data
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON for {symbol} @ {row['timestamp']}")

        logger.debug(f"Retrieved {len(result)} stock prices for {symbol}")
        return result

    def has_stock_prices(self, symbol: str, max_age_hours: Optional[float] = None) -> bool:
        """
        Check if we have cached stock prices for a symbol.

        Args:
            symbol: Stock ticker symbol
            max_age_hours: Maximum cache age in hours (None = no limit)

        Returns:
            True if cached data exists
        """
        symbol = symbol.upper()

        with self._get_connection() as conn:
            cursor = conn.cursor()

            query = """
                SELECT COUNT(*) as count
                FROM market_data
                WHERE symbol = ? AND data_type = ?
            """
            params: list[Any] = [symbol, self.DATA_TYPE_STOCK]

            if max_age_hours is not None:
                cutoff = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()
                query += " AND cached_at >= ?"
                params.append(cutoff)

            cursor.execute(query, params)
            row = cursor.fetchone()

        return row["count"] > 0 if row else False

    # ==================== Option Contract Methods ====================

    def set_option_contract(self, symbol: str, timestamp: str, contract: dict[str, Any]) -> None:
        """
        Store a single option contract.

        Args:
            symbol: Underlying stock ticker symbol
            timestamp: Retrieval timestamp in ISO format
            contract: Option contract data with required keys:
                      expiration_date, strike, option_type (Call/Put)

        Raises:
            CacheError: If data cannot be written
            ValueError: If required contract fields are missing
        """
        symbol = symbol.upper()
        cached_at = datetime.now().isoformat()

        # Validate required fields
        required = ["expiration_date", "strike", "option_type"]
        missing = [f for f in required if f not in contract]
        if missing:
            raise ValueError(f"Missing required contract fields: {missing}")

        expiration_date = contract["expiration_date"]
        strike = float(contract["strike"])
        option_type = contract["option_type"]

        try:
            json_data = json.dumps(contract)

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO market_data
                    (timestamp, symbol, data_type, json_data, expiration_date, strike, option_type, cached_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        timestamp,
                        symbol,
                        self.DATA_TYPE_OPTION,
                        json_data,
                        expiration_date,
                        strike,
                        option_type,
                        cached_at,
                    ),
                )
                conn.commit()

            logger.debug(f"Cached option: {symbol} {expiration_date} ${strike} {option_type}")

        except (sqlite3.Error, TypeError) as e:
            logger.error(f"Cache write error for option {symbol}: {e}")
            raise CacheError(f"Failed to cache option contract for {symbol}: {e}") from e

    def set_option_contracts(
        self, symbol: str, timestamp: str, contracts: list[dict[str, Any]]
    ) -> int:
        """
        Store multiple option contracts.

        Args:
            symbol: Underlying stock ticker symbol
            timestamp: Retrieval timestamp in ISO format
            contracts: List of option contract dictionaries

        Returns:
            Number of contracts stored

        Raises:
            CacheError: If data cannot be written
        """
        symbol = symbol.upper()
        cached_at = datetime.now().isoformat()
        count = 0
        errors = 0

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                for contract in contracts:
                    # Skip contracts missing required fields
                    if not all(k in contract for k in ["expiration_date", "strike", "option_type"]):
                        errors += 1
                        continue

                    json_data = json.dumps(contract)
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO market_data
                        (timestamp, symbol, data_type, json_data, expiration_date, strike, option_type, cached_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            timestamp,
                            symbol,
                            self.DATA_TYPE_OPTION,
                            json_data,
                            contract["expiration_date"],
                            float(contract["strike"]),
                            contract["option_type"],
                            cached_at,
                        ),
                    )
                    count += 1

                conn.commit()

            if errors > 0:
                logger.warning(f"Skipped {errors} invalid contracts for {symbol}")
            logger.debug(f"Cached {count} option contracts for {symbol}")
            return count

        except (sqlite3.Error, TypeError) as e:
            logger.error(f"Cache write error for option contracts {symbol}: {e}")
            raise CacheError(f"Failed to cache option contracts for {symbol}: {e}") from e

    def get_option_contracts(
        self,
        symbol: str,
        expiration_date: Optional[str] = None,
        strike: Optional[float] = None,
        option_type: Optional[str] = None,
        max_age_hours: Optional[float] = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve option contracts.

        Args:
            symbol: Underlying stock ticker symbol
            expiration_date: Optional filter by expiration date
            strike: Optional filter by strike price
            option_type: Optional filter by type ('Call' or 'Put')
            max_age_hours: Maximum cache age in hours (None = no limit)

        Returns:
            List of option contract dictionaries
        """
        symbol = symbol.upper()
        result = []

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Build query with optional filters
            query = """
                SELECT json_data, cached_at
                FROM market_data
                WHERE symbol = ? AND data_type = ?
            """
            params: list[Any] = [symbol, self.DATA_TYPE_OPTION]

            if expiration_date:
                query += " AND expiration_date = ?"
                params.append(expiration_date)

            if strike is not None:
                query += " AND strike = ?"
                params.append(strike)

            if option_type:
                query += " AND option_type = ?"
                params.append(option_type)

            if max_age_hours is not None:
                cutoff = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()
                query += " AND cached_at >= ?"
                params.append(cutoff)

            query += " ORDER BY expiration_date, strike, option_type"

            cursor.execute(query, params)
            rows = cursor.fetchall()

        for row in rows:
            try:
                data = json.loads(row["json_data"])
                result.append(data)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON for option contract {symbol}")

        logger.debug(f"Retrieved {len(result)} option contracts for {symbol}")
        return result

    # ==================== API Usage Tracking ====================

    def get_alpha_vantage_usage_today(self) -> int:
        """
        Get number of Alpha Vantage API calls made today.

        Returns:
            Number of API calls made today
        """
        today = datetime.now().strftime("%Y-%m-%d")

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT count FROM api_usage WHERE service = ? AND date = ?",
                ("alpha_vantage", today),
            )
            row = cursor.fetchone()

        return row["count"] if row else 0

    def increment_alpha_vantage_usage(self) -> int:
        """
        Increment and return today's Alpha Vantage usage count.

        Returns:
            Updated usage count for today
        """
        today = datetime.now().strftime("%Y-%m-%d")

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Use UPSERT pattern for atomic increment
            cursor.execute(
                """
                INSERT INTO api_usage (service, date, count)
                VALUES (?, ?, 1)
                ON CONFLICT(service, date) DO UPDATE SET count = count + 1
                """,
                ("alpha_vantage", today),
            )
            conn.commit()

            # Get updated count
            cursor.execute(
                "SELECT count FROM api_usage WHERE service = ? AND date = ?",
                ("alpha_vantage", today),
            )
            row = cursor.fetchone()

        return row["count"] if row else 1

    # ==================== Utility Methods ====================

    def delete_market_data(
        self,
        symbol: Optional[str] = None,
        data_type: Optional[str] = None,
        before_date: Optional[str] = None,
    ) -> int:
        """
        Delete market data entries.

        Args:
            symbol: Optional filter by symbol
            data_type: Optional filter by type ('stock' or 'option')
            before_date: Optional delete data with timestamp before this date

        Returns:
            Number of entries deleted
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            query = "DELETE FROM market_data WHERE 1=1"
            params: list[Any] = []

            if symbol:
                query += " AND symbol = ?"
                params.append(symbol.upper())

            if data_type:
                query += " AND data_type = ?"
                params.append(data_type)

            if before_date:
                query += " AND timestamp < ?"
                params.append(before_date)

            cursor.execute(query, params)
            conn.commit()
            count = cursor.rowcount

        if count > 0:
            logger.info(f"Deleted {count} market data entries")
        return count

    def clear_all(self) -> int:
        """
        Clear all market data (preserves API usage tracking).

        Returns:
            Number of entries deleted
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM market_data")
            count = cursor.fetchone()["count"]

            cursor.execute("DELETE FROM market_data")
            conn.commit()

        if count > 0:
            logger.info(f"Cleared {count} market data entries")
        return count

    def get_stats(self) -> dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Count by type
            cursor.execute("""
                SELECT data_type, COUNT(*) as count
                FROM market_data
                GROUP BY data_type
            """)
            type_counts = {row["data_type"]: row["count"] for row in cursor.fetchall()}

            # Count symbols
            cursor.execute("""
                SELECT COUNT(DISTINCT symbol) as symbols
                FROM market_data
            """)
            symbol_count = cursor.fetchone()["symbols"]

            # Date range
            cursor.execute("""
                SELECT MIN(timestamp) as oldest, MAX(timestamp) as newest
                FROM market_data
            """)
            row = cursor.fetchone()

            # Database size
            cursor.execute(
                "SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()"
            )
            db_size = cursor.fetchone()["size"]

        return {
            "stock_prices_count": type_counts.get(self.DATA_TYPE_STOCK, 0),
            "option_contracts_count": type_counts.get(self.DATA_TYPE_OPTION, 0),
            "total_entries": sum(type_counts.values()) if type_counts else 0,
            "unique_symbols": symbol_count,
            "oldest_data": row["oldest"],
            "newest_data": row["newest"],
            "database_size_bytes": db_size,
        }

    def cleanup_expired(self, max_age_hours: float) -> int:
        """
        Remove expired market data entries.

        Args:
            max_age_hours: Maximum age in hours

        Returns:
            Number of entries removed
        """
        cutoff_time = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM market_data WHERE cached_at < ?", (cutoff_time,))
            conn.commit()
            count = cursor.rowcount

        if count > 0:
            logger.info(f"Cleaned up {count} expired market data entries")
        return count
