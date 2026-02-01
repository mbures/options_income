"""Performance metrics database model.

Pre-calculated performance metrics for portfolios, wheels, and system-wide
aggregations. Enables fast analytics queries without real-time calculation.
"""

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from src.server.database.session import Base

if TYPE_CHECKING:
    from .portfolio import Portfolio
    from .wheel import Wheel


class PerformanceMetrics(Base):
    """Performance metrics model for analytics.

    Stores pre-calculated performance metrics for different aggregation
    levels (wheel, portfolio, system-wide) over specific time periods.
    This enables fast analytics queries and historical performance tracking.

    Attributes:
        id: Unique identifier (auto-incrementing integer)
        portfolio_id: Foreign key to Portfolio (NULL for system-wide)
        wheel_id: Foreign key to Wheel (NULL for portfolio/system aggregate)
        period_start: Start date of measurement period
        period_end: End date of measurement period
        total_premium: Total premium collected in period
        total_trades: Number of trades in period
        winning_trades: Number of trades that expired OTM
        losing_trades: Number of trades that were assigned
        win_rate: Win rate percentage (0-100)
        annualized_return: Annualized return percentage (if calculable)
        created_at: Timestamp when metrics were calculated
        portfolio: Relationship to Portfolio
        wheel: Relationship to Wheel
    """

    __tablename__ = "performance_metrics"

    # Columns
    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(
        String,
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    wheel_id = Column(
        Integer,
        ForeignKey("wheels.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    period_start = Column(Date, nullable=False, index=True)
    period_end = Column(Date, nullable=False, index=True)
    total_premium = Column(Float, nullable=False, default=0.0)
    total_trades = Column(Integer, nullable=False, default=0)
    winning_trades = Column(Integer, nullable=False, default=0)
    losing_trades = Column(Integer, nullable=False, default=0)
    win_rate = Column(Float, nullable=False, default=0.0)
    annualized_return = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    portfolio = relationship(
        "Portfolio",
        back_populates="performance_metrics",
        lazy="select"
    )
    wheel = relationship(
        "Wheel",
        back_populates="performance_metrics",
        lazy="select"
    )

    def __repr__(self) -> str:
        """String representation for debugging.

        Returns:
            Formatted string with metrics summary
        """
        scope = (
            f"wheel_id={self.wheel_id}" if self.wheel_id
            else f"portfolio_id={self.portfolio_id}" if self.portfolio_id
            else "system-wide"
        )
        return (
            f"<PerformanceMetrics(id={self.id}, {scope}, "
            f"period={self.period_start} to {self.period_end}, "
            f"trades={self.total_trades}, win_rate={self.win_rate:.1f}%)>"
        )
