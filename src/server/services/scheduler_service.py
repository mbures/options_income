"""Service for managing background task scheduler.

This module provides a service layer for APScheduler integration,
managing scheduled jobs, lifecycle, and persistence.
"""

import logging
from datetime import datetime
from typing import Optional

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.server.config import settings

logger = logging.getLogger(__name__)


class SchedulerService:
    """Service for managing background task scheduler.

    Wraps APScheduler BackgroundScheduler to provide lifecycle management,
    job persistence, and integration with FastAPI application.

    Attributes:
        scheduler: APScheduler BackgroundScheduler instance
        is_running: Whether scheduler is currently running
    """

    def __init__(self, db_url: Optional[str] = None):
        """Initialize scheduler service.

        Args:
            db_url: Optional database URL for job persistence.
                    Defaults to settings.database_url
        """
        self.scheduler: Optional[BackgroundScheduler] = None
        self.is_running = False
        self._db_url = db_url or settings.database_url

    def initialize(self) -> None:
        """Initialize the scheduler with configuration.

        Sets up:
        - SQLAlchemy jobstore for job persistence
        - Thread pool executor for job execution
        - Default configuration values
        """
        if self.scheduler is not None:
            logger.warning("Scheduler already initialized")
            return

        # Configure jobstores
        jobstores = {
            "default": SQLAlchemyJobStore(url=self._db_url, tablename="apscheduler_jobs")
        }

        # Configure executors
        executors = {
            "default": ThreadPoolExecutor(max_workers=5),
        }

        # Job defaults
        job_defaults = {
            "coalesce": True,  # Combine missed runs into one
            "max_instances": 1,  # Only one instance per job at a time
            "misfire_grace_time": 60,  # Allow 60s grace period for missed jobs
        }

        # Create scheduler
        self.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone="America/New_York",  # Market hours timezone
        )

        logger.info("Scheduler initialized successfully")

    def start(self) -> None:
        """Start the scheduler.

        Initializes scheduler if not already initialized, then starts it.
        Jobs will begin executing according to their schedules.

        Raises:
            RuntimeError: If scheduler fails to start
        """
        if self.is_running:
            logger.warning("Scheduler already running")
            return

        if self.scheduler is None:
            self.initialize()

        try:
            self.scheduler.start()
            self.is_running = True
            logger.info("Scheduler started successfully")
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
            raise RuntimeError(f"Failed to start scheduler: {e}")

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the scheduler.

        Args:
            wait: Whether to wait for running jobs to complete
        """
        if not self.is_running:
            logger.warning("Scheduler not running")
            return

        if self.scheduler is None:
            logger.warning("Scheduler not initialized")
            return

        try:
            self.scheduler.shutdown(wait=wait)
            self.is_running = False
            logger.info("Scheduler shutdown successfully")
        except Exception as e:
            logger.error(f"Error during scheduler shutdown: {e}")
            raise

    def add_job(
        self,
        func,
        trigger,
        id: Optional[str] = None,
        name: Optional[str] = None,
        replace_existing: bool = True,
        **trigger_args,
    ):
        """Add a job to the scheduler.

        Args:
            func: The callable to execute
            trigger: Trigger type ('interval', 'cron', 'date')
            id: Unique job identifier
            name: Human-readable job name
            replace_existing: Whether to replace existing job with same id
            **trigger_args: Additional trigger-specific arguments

        Returns:
            The added job instance

        Example:
            >>> service.add_job(
            >>>     my_task,
            >>>     'interval',
            >>>     id='my_task',
            >>>     minutes=5
            >>> )
        """
        if self.scheduler is None:
            raise RuntimeError("Scheduler not initialized")

        return self.scheduler.add_job(
            func=func,
            trigger=trigger,
            id=id,
            name=name,
            replace_existing=replace_existing,
            **trigger_args,
        )

    def remove_job(self, job_id: str) -> None:
        """Remove a job from the scheduler.

        Args:
            job_id: The job identifier

        Raises:
            JobLookupError: If job not found
        """
        if self.scheduler is None:
            raise RuntimeError("Scheduler not initialized")

        self.scheduler.remove_job(job_id)
        logger.info(f"Removed job: {job_id}")

    def get_job(self, job_id: str):
        """Get a job by ID.

        Args:
            job_id: The job identifier

        Returns:
            Job instance or None if not found
        """
        if self.scheduler is None:
            raise RuntimeError("Scheduler not initialized")

        return self.scheduler.get_job(job_id)

    def get_jobs(self):
        """Get all scheduled jobs.

        Returns:
            List of all job instances
        """
        if self.scheduler is None:
            raise RuntimeError("Scheduler not initialized")

        return self.scheduler.get_jobs()

    def pause_job(self, job_id: str) -> None:
        """Pause a job.

        Args:
            job_id: The job identifier
        """
        if self.scheduler is None:
            raise RuntimeError("Scheduler not initialized")

        self.scheduler.pause_job(job_id)
        logger.info(f"Paused job: {job_id}")

    def resume_job(self, job_id: str) -> None:
        """Resume a paused job.

        Args:
            job_id: The job identifier
        """
        if self.scheduler is None:
            raise RuntimeError("Scheduler not initialized")

        self.scheduler.resume_job(job_id)
        logger.info(f"Resumed job: {job_id}")

    def reschedule_job(self, job_id: str, trigger, **trigger_args):
        """Reschedule an existing job.

        Args:
            job_id: The job identifier
            trigger: New trigger type
            **trigger_args: New trigger arguments

        Returns:
            The rescheduled job instance
        """
        if self.scheduler is None:
            raise RuntimeError("Scheduler not initialized")

        job = self.scheduler.reschedule_job(
            job_id=job_id, trigger=trigger, **trigger_args
        )
        logger.info(f"Rescheduled job: {job_id}")
        return job

    def get_status(self) -> dict:
        """Get scheduler status information.

        Returns:
            Dictionary with scheduler status details
        """
        if self.scheduler is None:
            return {
                "initialized": False,
                "running": False,
                "jobs_count": 0,
                "state": "not_initialized",
            }

        jobs = self.get_jobs()
        return {
            "initialized": True,
            "running": self.is_running,
            "jobs_count": len(jobs),
            "state": str(self.scheduler.state),
            "timezone": str(self.scheduler.timezone),
        }


# Global scheduler service instance
_scheduler_service: Optional[SchedulerService] = None


def get_scheduler_service() -> SchedulerService:
    """Get the global scheduler service instance.

    Returns:
        SchedulerService instance
    """
    global _scheduler_service
    if _scheduler_service is None:
        _scheduler_service = SchedulerService()
    return _scheduler_service
