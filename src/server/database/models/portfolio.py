"""Portfolio database model.

Portfolio organizes wheels by strategy, account, or risk level.
Each portfolio can contain multiple wheels for different symbols.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, Float, String, Text
from sqlalchemy.orm import relationship

from src.server.database.session import Base

if TYPE_CHECKING:
    from .wheel import Wheel


class Portfolio(Base):
    """Portfolio model for organizing wheels.

    A portfolio groups wheels together for organizational purposes,
    such as by strategy type, account, or risk level. Each wheel
    can only belong to one portfolio, but the same symbol can exist
    in multiple portfolios.

    Attributes:
        id: Unique identifier (UUID as string)
        name: Human-readable portfolio name
        description: Optional detailed description
        default_capital: Default capital allocation for new wheels
        created_at: Timestamp when portfolio was created
        updated_at: Timestamp when portfolio was last modified
        wheels: Relationship to Wheel models in this portfolio
    """

    __tablename__ = "portfolios"

    # Columns
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    default_capital = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Relationships
    wheels = relationship(
        "Wheel",
        back_populates="portfolio",
        cascade="all, delete-orphan",
        lazy="select"
    )

    performance_metrics = relationship(
        "PerformanceMetrics",
        back_populates="portfolio",
        cascade="all, delete-orphan",
        lazy="select"
    )

    scheduler_configs = relationship(
        "SchedulerConfig",
        back_populates="portfolio",
        cascade="all, delete-orphan",
        lazy="select"
    )

    def __repr__(self) -> str:
        """String representation for debugging.

        Returns:
            Formatted string with portfolio ID and name
        """
        return f"<Portfolio(id={self.id}, name={self.name})>"
