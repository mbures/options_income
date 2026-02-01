"""Scheduler configuration database model.

Persists background task configuration, schedules, and execution state
for APScheduler jobs.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from src.server.database.session import Base

if TYPE_CHECKING:
    from .portfolio import Portfolio


class SchedulerConfig(Base):
    """Scheduler configuration model for background tasks.

    Stores configuration for scheduled tasks (APScheduler jobs),
    including schedule parameters, enable/disable state, and execution
    tracking. Tasks can be portfolio-specific or system-wide.

    Attributes:
        id: Unique identifier (auto-incrementing integer)
        portfolio_id: Foreign key to Portfolio (NULL for system-wide tasks)
        task_name: Name of the scheduled task (e.g., "price_refresh")
        enabled: Whether task is currently enabled
        schedule_type: Type of schedule ("interval" or "cron")
        schedule_params: JSON string with schedule parameters
        last_run: Timestamp of last successful execution
        next_run: Timestamp of next scheduled execution
        created_at: Timestamp when config was created
        updated_at: Timestamp when config was last modified
        portfolio: Relationship to Portfolio
    """

    __tablename__ = "scheduler_config"

    # Columns
    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(
        String,
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    task_name = Column(String, nullable=False, index=True)
    enabled = Column(Boolean, nullable=False, default=True)
    schedule_type = Column(String, nullable=False)  # "interval" or "cron"
    schedule_params = Column(Text, nullable=False)  # JSON string
    last_run = Column(DateTime, nullable=True)
    next_run = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Relationships
    portfolio = relationship(
        "Portfolio",
        back_populates="scheduler_configs",
        lazy="select"
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "portfolio_id",
            "task_name",
            name="uq_portfolio_task"
        ),
    )

    def __repr__(self) -> str:
        """String representation for debugging.

        Returns:
            Formatted string with scheduler config details
        """
        scope = (
            f"portfolio_id={self.portfolio_id}"
            if self.portfolio_id
            else "system-wide"
        )
        return (
            f"<SchedulerConfig(id={self.id}, task={self.task_name}, "
            f"{scope}, enabled={self.enabled})>"
        )
