"""Repository for job execution history operations.

Provides database access layer for job execution records,
including creating execution records and retrieving history.
"""

import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from src.server.database.models.job_execution import JobExecution

logger = logging.getLogger(__name__)


class JobExecutionRepository:
    """Repository for managing job execution history.

    Handles CRUD operations for job execution records,
    including execution tracking and history retrieval.
    """

    def __init__(self, db: Session):
        """Initialize repository with database session.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def create_execution(
        self,
        job_id: str,
        job_name: str,
        started_at: datetime,
    ) -> JobExecution:
        """Create a new job execution record.

        Args:
            job_id: APScheduler job ID
            job_name: Human-readable job name
            started_at: Execution start time

        Returns:
            Created JobExecution instance
        """
        execution = JobExecution(
            job_id=job_id,
            job_name=job_name,
            started_at=started_at,
            status="running",
        )
        self.db.add(execution)
        self.db.commit()
        self.db.refresh(execution)
        logger.info(f"Created execution record for job {job_name} (id={execution.id})")
        return execution

    def finish_execution(
        self,
        execution_id: int,
        finished_at: datetime,
        status: str,
        error_message: Optional[str] = None,
    ) -> Optional[JobExecution]:
        """Mark execution as finished with status.

        Args:
            execution_id: Execution record ID
            finished_at: Execution finish time
            status: Status ("success" or "failure")
            error_message: Error message if status is failure

        Returns:
            Updated JobExecution instance or None if not found
        """
        execution = self.db.query(JobExecution).filter(JobExecution.id == execution_id).first()
        if not execution:
            logger.warning(f"Execution {execution_id} not found")
            return None

        execution.finished_at = finished_at
        execution.status = status
        execution.error_message = error_message
        execution.duration_seconds = (finished_at - execution.started_at).total_seconds()

        self.db.commit()
        self.db.refresh(execution)
        logger.info(f"Finished execution {execution_id} with status {status}")
        return execution

    def get_execution(self, execution_id: int) -> Optional[JobExecution]:
        """Get execution record by ID.

        Args:
            execution_id: Execution record ID

        Returns:
            JobExecution instance or None if not found
        """
        return self.db.query(JobExecution).filter(JobExecution.id == execution_id).first()

    def list_executions(
        self,
        job_id: Optional[str] = None,
        job_name: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[JobExecution]:
        """List job execution records with optional filters.

        Args:
            job_id: Filter by job ID
            job_name: Filter by job name
            status: Filter by status
            limit: Maximum number of records to return
            offset: Number of records to skip

        Returns:
            List of JobExecution instances
        """
        query = self.db.query(JobExecution)

        if job_id:
            query = query.filter(JobExecution.job_id == job_id)
        if job_name:
            query = query.filter(JobExecution.job_name == job_name)
        if status:
            query = query.filter(JobExecution.status == status)

        query = query.order_by(JobExecution.started_at.desc())
        query = query.limit(limit).offset(offset)

        return query.all()

    def count_executions(
        self,
        job_id: Optional[str] = None,
        job_name: Optional[str] = None,
        status: Optional[str] = None,
    ) -> int:
        """Count job execution records with optional filters.

        Args:
            job_id: Filter by job ID
            job_name: Filter by job name
            status: Filter by status

        Returns:
            Total count of matching records
        """
        query = self.db.query(JobExecution)

        if job_id:
            query = query.filter(JobExecution.job_id == job_id)
        if job_name:
            query = query.filter(JobExecution.job_name == job_name)
        if status:
            query = query.filter(JobExecution.status == status)

        return query.count()

    def get_last_execution(self, job_id: str) -> Optional[JobExecution]:
        """Get the most recent execution for a job.

        Args:
            job_id: Job ID to query

        Returns:
            Most recent JobExecution or None
        """
        return (
            self.db.query(JobExecution)
            .filter(JobExecution.job_id == job_id)
            .order_by(JobExecution.started_at.desc())
            .first()
        )

    def delete_old_executions(self, days: int = 30) -> int:
        """Delete execution records older than specified days.

        Args:
            days: Number of days to retain

        Returns:
            Number of records deleted
        """
        from datetime import timedelta

        cutoff_date = datetime.utcnow() - timedelta(days=days)
        count = (
            self.db.query(JobExecution)
            .filter(JobExecution.started_at < cutoff_date)
            .delete()
        )
        self.db.commit()
        logger.info(f"Deleted {count} execution records older than {days} days")
        return count
