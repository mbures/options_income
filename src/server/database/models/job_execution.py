"""Job execution history database model.

Tracks execution history for scheduled background tasks, including
start/end times, success/failure status, and error messages.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from src.server.database.session import Base


class JobExecution(Base):
    """Job execution history model.

    Records each execution of a scheduled task for monitoring
    and debugging purposes.

    Attributes:
        id: Unique identifier (auto-incrementing integer)
        job_id: APScheduler job ID
        job_name: Human-readable job name
        started_at: Timestamp when job execution started
        finished_at: Timestamp when job execution finished (NULL if running)
        duration_seconds: Execution duration in seconds
        status: Execution status ("success", "failure", "running")
        error_message: Error message if execution failed
        created_at: Timestamp when record was created
    """

    __tablename__ = "job_executions"

    # Columns
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, nullable=False, index=True)
    job_name = Column(String, nullable=False, index=True)
    started_at = Column(DateTime, nullable=False, index=True)
    finished_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    status = Column(String, nullable=False, default="running")  # running, success, failure
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        """String representation for debugging.

        Returns:
            Formatted string with job execution details
        """
        return (
            f"<JobExecution(id={self.id}, job={self.job_name}, "
            f"status={self.status}, started={self.started_at})>"
        )
