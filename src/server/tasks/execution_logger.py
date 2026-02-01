"""Task execution logging decorator.

Provides a decorator to automatically log task execution to the database,
including start/end times, status, and error messages.
"""

import functools
import logging
from datetime import datetime
from typing import Callable

from src.server.database.session import get_session_factory
from src.server.repositories.job_execution import JobExecutionRepository

logger = logging.getLogger(__name__)


def log_execution(job_id: str, job_name: str) -> Callable:
    """Decorator to log task execution to database.

    Wraps a task function to automatically create execution records
    with timing, status, and error information.

    Args:
        job_id: APScheduler job ID
        job_name: Human-readable job name

    Returns:
        Decorated function that logs execution

    Example:
        >>> @log_execution("price_refresh", "Price Refresh Task")
        >>> def price_refresh_task():
        >>>     # Task implementation
        >>>     pass
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Get database session
            SessionLocal = get_session_factory()
            db = SessionLocal()
            exec_repo = JobExecutionRepository(db)

            # Create execution record
            started_at = datetime.utcnow()
            execution = exec_repo.create_execution(
                job_id=job_id,
                job_name=job_name,
                started_at=started_at,
            )

            try:
                # Execute task
                result = func(*args, **kwargs)

                # Mark as successful
                finished_at = datetime.utcnow()
                exec_repo.finish_execution(
                    execution_id=execution.id,
                    finished_at=finished_at,
                    status="success",
                )

                return result

            except Exception as e:
                # Mark as failed
                finished_at = datetime.utcnow()
                exec_repo.finish_execution(
                    execution_id=execution.id,
                    finished_at=finished_at,
                    status="failure",
                    error_message=str(e),
                )

                # Re-raise exception
                logger.error(f"Task {job_name} failed: {e}", exc_info=True)
                raise

            finally:
                db.close()

        return wrapper

    return decorator
