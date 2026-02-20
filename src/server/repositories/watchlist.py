"""Repository for watchlist data access operations."""

import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from src.server.database.models.watchlist import WatchlistItem

logger = logging.getLogger(__name__)


class WatchlistRepository:
    """Repository for watchlist CRUD operations."""

    def __init__(self, db: Session):
        self.db = db

    def add_symbol(self, symbol: str, notes: Optional[str] = None) -> WatchlistItem:
        """Add a symbol to the watchlist.

        Args:
            symbol: Stock ticker (should already be uppercased)
            notes: Optional user notes

        Returns:
            Created WatchlistItem

        Raises:
            ValueError: If symbol already exists on watchlist
        """
        existing = self.get_by_symbol(symbol)
        if existing:
            raise ValueError(f"{symbol} is already on the watchlist")

        item = WatchlistItem(symbol=symbol, notes=notes)
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        logger.info(f"Added {symbol} to watchlist")
        return item

    def remove_symbol(self, symbol: str) -> bool:
        """Remove a symbol from the watchlist.

        Returns:
            True if removed, False if not found
        """
        item = self.get_by_symbol(symbol)
        if not item:
            return False
        self.db.delete(item)
        self.db.commit()
        logger.info(f"Removed {symbol} from watchlist")
        return True

    def list_all(self) -> List[WatchlistItem]:
        """List all watchlist symbols, ordered by symbol."""
        return (
            self.db.query(WatchlistItem)
            .order_by(WatchlistItem.symbol)
            .all()
        )

    def get_by_symbol(self, symbol: str) -> Optional[WatchlistItem]:
        """Get a watchlist item by symbol."""
        return (
            self.db.query(WatchlistItem)
            .filter(WatchlistItem.symbol == symbol.upper())
            .first()
        )
