"""Wheel position database model.

Represents a wheel strategy position on a single symbol within a portfolio.
Tracks state, capital allocation, share holdings, and trading profile.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from src.server.database.session import Base

if TYPE_CHECKING:
    from .performance import PerformanceMetrics
    from .portfolio import Portfolio
    from .snapshot import Snapshot
    from .trade import Trade


class Wheel(Base):
    """Wheel position model for a symbol in a portfolio.

    Represents a single wheel strategy position, tracking its state
    through the wheel cycle (cash → put open → shares → call open → cash).
    Each wheel belongs to exactly one portfolio, but the same symbol
    can have separate wheels in different portfolios.

    Attributes:
        id: Unique identifier (auto-incrementing integer)
        portfolio_id: Foreign key to Portfolio
        symbol: Stock ticker symbol (e.g., "AAPL")
        state: Current wheel state (e.g., "cash", "cash_put_open", "shares")
        shares_held: Number of shares currently held (0 or 100)
        capital_allocated: Amount of capital allocated to this wheel
        cost_basis: Average cost per share when holding shares
        profile: Strike selection profile (e.g., "conservative", "aggressive")
        created_at: Timestamp when wheel was initialized
        updated_at: Timestamp when wheel was last modified
        is_active: Whether wheel is currently active (soft delete flag)
        portfolio: Relationship to Portfolio
        trades: Relationship to Trade records
        snapshots: Relationship to position snapshots
        performance_metrics: Relationship to performance metrics
    """

    __tablename__ = "wheels"

    # Columns
    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(
        String,
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    symbol = Column(String, nullable=False, index=True)
    state = Column(String, nullable=False, default="cash")
    shares_held = Column(Integer, nullable=False, default=0)
    capital_allocated = Column(Float, nullable=False, default=0.0)
    cost_basis = Column(Float, nullable=True)
    profile = Column(String, nullable=False, default="conservative")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    # Relationships
    portfolio = relationship("Portfolio", back_populates="wheels", lazy="select")
    trades = relationship(
        "Trade",
        back_populates="wheel",
        cascade="all, delete-orphan",
        lazy="select",
        order_by="desc(Trade.opened_at)"
    )
    snapshots = relationship(
        "Snapshot",
        back_populates="wheel",
        cascade="all, delete-orphan",
        lazy="select"
    )
    performance_metrics = relationship(
        "PerformanceMetrics",
        back_populates="wheel",
        cascade="all, delete-orphan",
        lazy="select"
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint("portfolio_id", "symbol", name="uq_portfolio_symbol"),
    )

    def __repr__(self) -> str:
        """String representation for debugging.

        Returns:
            Formatted string with wheel ID, portfolio ID, and symbol
        """
        return (
            f"<Wheel(id={self.id}, portfolio_id={self.portfolio_id}, "
            f"symbol={self.symbol}, state={self.state})>"
        )
