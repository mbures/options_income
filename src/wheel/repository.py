"""SQLite persistence layer for wheel strategy data."""

import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator, Optional

from src.models.profiles import StrikeProfile

from .models import TradeRecord, WheelPerformance, WheelPosition
from .state import TradeOutcome, WheelState

logger = logging.getLogger(__name__)


class WheelRepository:
    """SQLite persistence for wheel positions and trades."""

    def __init__(self, db_path: str = "~/.wheel_strategy/trades.db"):
        """
        Initialize the repository.

        Args:
            db_path: Path to SQLite database file. Supports ~ expansion.
        """
        self.db_path = os.path.expanduser(db_path)
        self._ensure_directory()
        self._init_database()

    def _ensure_directory(self) -> None:
        """Create database directory if it doesn't exist."""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            logger.info(f"Created database directory: {db_dir}")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_database(self) -> None:
        """Create tables if they don't exist."""
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS wheels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL UNIQUE,
                    state TEXT NOT NULL DEFAULT 'cash',
                    capital_allocated REAL NOT NULL DEFAULT 0,
                    shares_held INTEGER NOT NULL DEFAULT 0,
                    cost_basis REAL,
                    profile TEXT NOT NULL DEFAULT 'conservative',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    wheel_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    strike REAL NOT NULL,
                    expiration_date TEXT NOT NULL,
                    premium_per_share REAL NOT NULL,
                    contracts INTEGER NOT NULL,
                    total_premium REAL NOT NULL,
                    opened_at TEXT NOT NULL,
                    closed_at TEXT,
                    outcome TEXT NOT NULL DEFAULT 'open',
                    price_at_expiry REAL,
                    close_price REAL,
                    FOREIGN KEY (wheel_id) REFERENCES wheels(id)
                );

                CREATE INDEX IF NOT EXISTS idx_trades_wheel
                    ON trades(wheel_id);
                CREATE INDEX IF NOT EXISTS idx_trades_symbol
                    ON trades(symbol);
                CREATE INDEX IF NOT EXISTS idx_trades_outcome
                    ON trades(outcome);
                CREATE INDEX IF NOT EXISTS idx_wheels_symbol
                    ON wheels(symbol);
                CREATE INDEX IF NOT EXISTS idx_wheels_active
                    ON wheels(is_active);
            """
            )
        logger.debug(f"Database initialized at {self.db_path}")

    # Wheel operations

    def create_wheel(self, position: WheelPosition) -> WheelPosition:
        """
        Create a new wheel position.

        Args:
            position: WheelPosition to create (id will be set).

        Returns:
            WheelPosition with assigned id.

        Raises:
            sqlite3.IntegrityError: If symbol already exists.
        """
        now = datetime.now().isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO wheels
                (symbol, state, capital_allocated, shares_held, cost_basis,
                 profile, created_at, updated_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    position.symbol.upper(),
                    position.state.value,
                    position.capital_allocated,
                    position.shares_held,
                    position.cost_basis,
                    position.profile.value,
                    now,
                    now,
                    1 if position.is_active else 0,
                ),
            )
            position.id = cursor.lastrowid
            position.created_at = datetime.fromisoformat(now)
            position.updated_at = datetime.fromisoformat(now)
        logger.info(f"Created wheel position for {position.symbol}")
        return position

    def get_wheel(self, symbol: str) -> Optional[WheelPosition]:
        """
        Get a wheel position by symbol.

        Args:
            symbol: Stock ticker symbol.

        Returns:
            WheelPosition if found, None otherwise.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM wheels WHERE symbol = ? AND is_active = 1",
                (symbol.upper(),),
            ).fetchone()
            if row:
                return self._row_to_position(row)
        return None

    def get_wheel_by_id(self, wheel_id: int) -> Optional[WheelPosition]:
        """Get a wheel position by ID."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM wheels WHERE id = ?", (wheel_id,)
            ).fetchone()
            if row:
                return self._row_to_position(row)
        return None

    def update_wheel(self, position: WheelPosition) -> None:
        """
        Update an existing wheel position.

        Args:
            position: WheelPosition with updated values.
        """
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE wheels
                SET state = ?, capital_allocated = ?, shares_held = ?,
                    cost_basis = ?, profile = ?, updated_at = ?, is_active = ?
                WHERE id = ?
                """,
                (
                    position.state.value,
                    position.capital_allocated,
                    position.shares_held,
                    position.cost_basis,
                    position.profile.value,
                    now,
                    1 if position.is_active else 0,
                    position.id,
                ),
            )
        position.updated_at = datetime.fromisoformat(now)
        logger.debug(f"Updated wheel {position.symbol} to state {position.state.value}")

    def list_wheels(self, active_only: bool = True) -> list[WheelPosition]:
        """
        List all wheel positions.

        Args:
            active_only: If True, only return active wheels.

        Returns:
            List of WheelPosition objects.
        """
        with self._connect() as conn:
            if active_only:
                rows = conn.execute(
                    "SELECT * FROM wheels WHERE is_active = 1 ORDER BY symbol"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM wheels ORDER BY symbol"
                ).fetchall()
            return [self._row_to_position(row) for row in rows]

    def delete_wheel(self, symbol: str) -> bool:
        """
        Soft delete a wheel (mark as inactive).

        Args:
            symbol: Stock ticker symbol.

        Returns:
            True if deleted, False if not found.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE wheels SET is_active = 0, updated_at = ? WHERE symbol = ?",
                (datetime.now().isoformat(), symbol.upper()),
            )
            deleted = cursor.rowcount > 0
        if deleted:
            logger.info(f"Deactivated wheel for {symbol}")
        return deleted

    def _row_to_position(self, row: sqlite3.Row) -> WheelPosition:
        """Convert a database row to a WheelPosition."""
        return WheelPosition(
            id=row["id"],
            symbol=row["symbol"],
            state=WheelState(row["state"]),
            capital_allocated=row["capital_allocated"],
            shares_held=row["shares_held"],
            cost_basis=row["cost_basis"],
            profile=StrikeProfile(row["profile"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            is_active=bool(row["is_active"]),
        )

    # Trade operations

    def create_trade(self, trade: TradeRecord) -> TradeRecord:
        """
        Create a new trade record.

        Args:
            trade: TradeRecord to create (id will be set).

        Returns:
            TradeRecord with assigned id.
        """
        now = datetime.now().isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO trades
                (wheel_id, symbol, direction, strike, expiration_date,
                 premium_per_share, contracts, total_premium, opened_at,
                 closed_at, outcome, price_at_expiry, close_price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade.wheel_id,
                    trade.symbol.upper(),
                    trade.direction,
                    trade.strike,
                    trade.expiration_date,
                    trade.premium_per_share,
                    trade.contracts,
                    trade.total_premium,
                    now,
                    trade.closed_at.isoformat() if trade.closed_at else None,
                    trade.outcome.value,
                    trade.price_at_expiry,
                    trade.close_price,
                ),
            )
            trade.id = cursor.lastrowid
            trade.opened_at = datetime.fromisoformat(now)
        logger.info(
            f"Created trade: {trade.direction} {trade.contracts}x "
            f"{trade.symbol} ${trade.strike}"
        )
        return trade

    def get_open_trade(self, wheel_id: int) -> Optional[TradeRecord]:
        """
        Get the currently open trade for a wheel.

        Args:
            wheel_id: ID of the wheel position.

        Returns:
            TradeRecord if found, None otherwise.
        """
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM trades
                WHERE wheel_id = ? AND outcome = 'open'
                ORDER BY opened_at DESC LIMIT 1
                """,
                (wheel_id,),
            ).fetchone()
            if row:
                return self._row_to_trade(row)
        return None

    def update_trade(self, trade: TradeRecord) -> None:
        """
        Update an existing trade record.

        Args:
            trade: TradeRecord with updated values.
        """
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE trades
                SET closed_at = ?, outcome = ?, price_at_expiry = ?, close_price = ?
                WHERE id = ?
                """,
                (
                    trade.closed_at.isoformat() if trade.closed_at else None,
                    trade.outcome.value,
                    trade.price_at_expiry,
                    trade.close_price,
                    trade.id,
                ),
            )
        logger.debug(f"Updated trade {trade.id} to outcome {trade.outcome.value}")

    def get_trades(
        self,
        symbol: Optional[str] = None,
        wheel_id: Optional[int] = None,
        outcome: Optional[TradeOutcome] = None,
    ) -> list[TradeRecord]:
        """
        Get trades with optional filters.

        Args:
            symbol: Filter by symbol.
            wheel_id: Filter by wheel ID.
            outcome: Filter by outcome.

        Returns:
            List of matching TradeRecord objects.
        """
        query = "SELECT * FROM trades WHERE 1=1"
        params: list = []

        if symbol:
            query += " AND symbol = ?"
            params.append(symbol.upper())
        if wheel_id is not None:
            query += " AND wheel_id = ?"
            params.append(wheel_id)
        if outcome:
            query += " AND outcome = ?"
            params.append(outcome.value)

        query += " ORDER BY opened_at DESC"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_trade(row) for row in rows]

    def get_all_trades(self) -> list[TradeRecord]:
        """Get all trades across all wheels."""
        return self.get_trades()

    def _row_to_trade(self, row: sqlite3.Row) -> TradeRecord:
        """Convert a database row to a TradeRecord."""
        return TradeRecord(
            id=row["id"],
            wheel_id=row["wheel_id"],
            symbol=row["symbol"],
            direction=row["direction"],
            strike=row["strike"],
            expiration_date=row["expiration_date"],
            premium_per_share=row["premium_per_share"],
            contracts=row["contracts"],
            total_premium=row["total_premium"],
            opened_at=datetime.fromisoformat(row["opened_at"]),
            closed_at=(
                datetime.fromisoformat(row["closed_at"]) if row["closed_at"] else None
            ),
            outcome=TradeOutcome(row["outcome"]),
            price_at_expiry=row["price_at_expiry"],
            close_price=row["close_price"],
        )

    # Utility methods

    def get_trade_count(self, wheel_id: int) -> int:
        """Get total trade count for a wheel."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as count FROM trades WHERE wheel_id = ?",
                (wheel_id,),
            ).fetchone()
            return row["count"] if row else 0

    def get_total_premium(self, wheel_id: Optional[int] = None) -> float:
        """Get total premium collected for a wheel or all wheels."""
        with self._connect() as conn:
            if wheel_id:
                row = conn.execute(
                    "SELECT SUM(total_premium) as total FROM trades WHERE wheel_id = ?",
                    (wheel_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT SUM(total_premium) as total FROM trades"
                ).fetchone()
            return row["total"] if row and row["total"] else 0.0
