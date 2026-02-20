"""Watchlist item database model.

Represents a symbol on the user's watchlist for opportunity scanning.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from src.server.database.session import Base


class WatchlistItem(Base):
    """Watchlist item model for tracking symbols to scan.

    Attributes:
        id: Unique identifier (auto-incrementing integer)
        symbol: Stock ticker symbol (unique, indexed)
        notes: Optional user notes about this symbol
        created_at: Timestamp when symbol was added to watchlist
    """

    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False, unique=True, index=True)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<WatchlistItem(id={self.id}, symbol={self.symbol})>"
