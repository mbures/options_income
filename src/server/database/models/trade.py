"""Trade record database model.

Records individual option trades (puts and calls) within a wheel.
Tracks opening details, expiration outcomes, and P&L.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from src.server.database.session import Base

if TYPE_CHECKING:
    from .snapshot import Snapshot
    from .wheel import Wheel


class Trade(Base):
    """Trade record model for option trades.

    Represents a single option trade (selling a put or call) within
    a wheel strategy. Tracks all details from opening through to
    expiration or early close, including outcomes and P&L.

    Attributes:
        id: Unique identifier (auto-incrementing integer)
        wheel_id: Foreign key to Wheel
        symbol: Stock ticker symbol (denormalized for queries)
        direction: Option type ("put" or "call")
        strike: Strike price of the option
        expiration_date: Expiration date (ISO format YYYY-MM-DD)
        premium_per_share: Premium collected per share
        contracts: Number of contracts (100 shares each)
        total_premium: Total premium collected (premium_per_share * contracts * 100)
        opened_at: Timestamp when trade was opened
        closed_at: Timestamp when trade was closed (if applicable)
        outcome: Trade outcome ("open", "expired", "assigned", "called_away", "closed_early")
        price_at_expiry: Stock price at expiration (if applicable)
        close_price: Premium paid to close early (if applicable)
        wheel: Relationship to Wheel
        snapshots: Relationship to position snapshots
    """

    __tablename__ = "trades"

    # Columns
    id = Column(Integer, primary_key=True, autoincrement=True)
    wheel_id = Column(
        Integer,
        ForeignKey("wheels.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    symbol = Column(String, nullable=False, index=True)
    direction = Column(String, nullable=False)  # "put" or "call"
    strike = Column(Float, nullable=False)
    expiration_date = Column(String, nullable=False, index=True)
    premium_per_share = Column(Float, nullable=False)
    contracts = Column(Integer, nullable=False)
    total_premium = Column(Float, nullable=False)
    opened_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    closed_at = Column(DateTime, nullable=True)
    outcome = Column(String, nullable=False, default="open", index=True)
    price_at_expiry = Column(Float, nullable=True)
    close_price = Column(Float, nullable=True)

    # Relationships
    wheel = relationship("Wheel", back_populates="trades", lazy="select")
    snapshots = relationship(
        "Snapshot",
        back_populates="trade",
        cascade="all, delete-orphan",
        lazy="select",
        order_by="Snapshot.snapshot_date"
    )

    def __repr__(self) -> str:
        """String representation for debugging.

        Returns:
            Formatted string with trade details
        """
        return (
            f"<Trade(id={self.id}, symbol={self.symbol}, "
            f"direction={self.direction}, strike={self.strike}, "
            f"expiration={self.expiration_date}, outcome={self.outcome})>"
        )
