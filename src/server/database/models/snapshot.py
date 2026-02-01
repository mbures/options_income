"""Position snapshot database model.

Records daily historical snapshots of open positions for trend analysis
and performance tracking over time.
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
    from .trade import Trade
    from .wheel import Wheel


class Snapshot(Base):
    """Position snapshot model for historical tracking.

    Captures the state of an open position at a specific point in time,
    typically at end-of-day. Enables tracking of position evolution,
    price movements, moneyness changes, and risk progression over time.

    Attributes:
        id: Unique identifier (auto-incrementing integer)
        trade_id: Foreign key to Trade
        wheel_id: Foreign key to Wheel (denormalized for queries)
        snapshot_date: Date of snapshot (ISO format YYYY-MM-DD)
        current_price: Stock price at snapshot time
        dte_calendar: Calendar days to expiration
        dte_trading: Trading days to expiration
        moneyness_pct: Percentage distance from strike (positive = OTM)
        is_itm: Whether option is in-the-money (assignment risk)
        risk_level: Risk assessment ("LOW", "MEDIUM", "HIGH")
        created_at: Timestamp when snapshot was created
        trade: Relationship to Trade
        wheel: Relationship to Wheel
    """

    __tablename__ = "snapshots"

    # Columns
    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_id = Column(
        Integer,
        ForeignKey("trades.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    wheel_id = Column(
        Integer,
        ForeignKey("wheels.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    snapshot_date = Column(String, nullable=False, index=True)
    current_price = Column(Float, nullable=False)
    dte_calendar = Column(Integer, nullable=False)
    dte_trading = Column(Integer, nullable=False)
    moneyness_pct = Column(Float, nullable=False)
    is_itm = Column(Boolean, nullable=False)
    risk_level = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    trade = relationship("Trade", back_populates="snapshots", lazy="select")
    wheel = relationship("Wheel", back_populates="snapshots", lazy="select")

    # Constraints
    __table_args__ = (
        UniqueConstraint("trade_id", "snapshot_date", name="uq_trade_snapshot_date"),
    )

    def __repr__(self) -> str:
        """String representation for debugging.

        Returns:
            Formatted string with snapshot details
        """
        return (
            f"<Snapshot(id={self.id}, trade_id={self.trade_id}, "
            f"date={self.snapshot_date}, price={self.current_price}, "
            f"risk={self.risk_level})>"
        )
