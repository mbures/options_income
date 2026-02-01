"""Scheduler management API endpoints.

Provides REST endpoints for managing scheduled background tasks,
including listing jobs, updating schedules, manual triggering, and
viewing execution history.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.server.database.session import get_db
from src.server.models.scheduler import (
    JobExecutionHistoryResponse,
    JobExecutionResponse,
    JobInfoResponse,
    JobListResponse,
    JobScheduleUpdate,
    JobTriggerResponse,
)
from src.server.repositories.job_execution import JobExecutionRepository
from src.server.services.scheduler_service import get_scheduler_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/scheduler",
    tags=["scheduler"],
)


def _format_schedule_description(job) -> str:
    """Format job schedule as human-readable string.

    Args:
        job: APScheduler job instance

    Returns:
        Human-readable schedule description
    """
    trigger = job.trigger
    trigger_type = type(trigger).__name__

    if trigger_type == "IntervalTrigger":
        interval = trigger.interval
        if interval.days > 0:
            return f"Every {interval.days} day(s)"
        elif interval.seconds >= 3600:
            hours = interval.seconds // 3600
            return f"Every {hours} hour(s)"
        elif interval.seconds >= 60:
            minutes = interval.seconds // 60
            return f"Every {minutes} minute(s)"
        else:
            return f"Every {interval.seconds} second(s)"
    elif trigger_type == "CronTrigger":
        # Format cron trigger - use str() as a simple solution
        # CronTrigger has complex internal fields, easier to use its string representation
        return f"Cron: {str(trigger)}"
    else:
        return f"{trigger_type}"


@router.get(
    "/jobs",
    response_model=JobListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all scheduled jobs",
    description="Returns list of all registered scheduled jobs with their status",
)
async def list_jobs(db: Session = Depends(get_db)) -> JobListResponse:
    """List all scheduled jobs.

    Returns:
        List of all jobs with their schedules and status
    """
    try:
        scheduler = get_scheduler_service()
        jobs = scheduler.get_jobs()

        # Get execution repository to fetch last run info
        exec_repo = JobExecutionRepository(db)

        job_infos = []
        for job in jobs:
            # Get last execution for this job
            last_execution = exec_repo.get_last_execution(job.id)

            job_info = JobInfoResponse(
                id=job.id,
                name=job.name or job.id,
                func=job.func_ref,
                trigger=type(job.trigger).__name__,
                next_run_time=job.next_run_time,
                last_run_time=last_execution.finished_at if last_execution else None,
                last_status=last_execution.status if last_execution else None,
                schedule_description=_format_schedule_description(job),
                enabled=True,  # Jobs in scheduler are always enabled
                misfire_grace_time=job.misfire_grace_time,
                max_instances=job.max_instances,
            )
            job_infos.append(job_info)

        return JobListResponse(jobs=job_infos, total=len(job_infos))

    except Exception as e:
        logger.error(f"Failed to list jobs: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve jobs: {str(e)}",
        )


@router.get(
    "/jobs/{job_id}",
    response_model=JobInfoResponse,
    status_code=status.HTTP_200_OK,
    summary="Get job details",
    description="Returns detailed information about a specific scheduled job",
)
async def get_job(job_id: str, db: Session = Depends(get_db)) -> JobInfoResponse:
    """Get details for a specific job.

    Args:
        job_id: Job ID to retrieve

    Returns:
        Job details

    Raises:
        HTTPException: If job not found
    """
    try:
        scheduler = get_scheduler_service()
        job = scheduler.get_job(job_id)

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {job_id} not found",
            )

        # Get last execution
        exec_repo = JobExecutionRepository(db)
        last_execution = exec_repo.get_last_execution(job.id)

        return JobInfoResponse(
            id=job.id,
            name=job.name or job.id,
            func=job.func_ref,
            trigger=type(job.trigger).__name__,
            next_run_time=job.next_run_time,
            last_run_time=last_execution.finished_at if last_execution else None,
            last_status=last_execution.status if last_execution else None,
            schedule_description=_format_schedule_description(job),
            enabled=True,
            misfire_grace_time=job.misfire_grace_time,
            max_instances=job.max_instances,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job {job_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve job: {str(e)}",
        )


@router.put(
    "/jobs/{job_id}",
    response_model=JobInfoResponse,
    status_code=status.HTTP_200_OK,
    summary="Update job schedule",
    description="Updates the schedule or enabled status of a scheduled job",
)
async def update_job_schedule(
    job_id: str,
    update: JobScheduleUpdate,
    db: Session = Depends(get_db),
) -> JobInfoResponse:
    """Update job schedule or enabled status.

    Args:
        job_id: Job ID to update
        update: Schedule update parameters

    Returns:
        Updated job details

    Raises:
        HTTPException: If job not found or update fails
    """
    try:
        scheduler = get_scheduler_service()
        job = scheduler.get_job(job_id)

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {job_id} not found",
            )

        # Handle pause/resume
        if update.enabled is not None:
            if update.enabled:
                scheduler.resume_job(job_id)
                logger.info(f"Resumed job {job_id}")
            else:
                scheduler.pause_job(job_id)
                logger.info(f"Paused job {job_id}")

        # Handle schedule update
        if update.trigger and update.schedule_params:
            scheduler.reschedule_job(
                job_id=job_id,
                trigger=update.trigger,
                **update.schedule_params,
            )
            logger.info(f"Rescheduled job {job_id} with trigger={update.trigger}")

        # Get updated job
        job = scheduler.get_job(job_id)
        exec_repo = JobExecutionRepository(db)
        last_execution = exec_repo.get_last_execution(job.id)

        return JobInfoResponse(
            id=job.id,
            name=job.name or job.id,
            func=job.func_ref,
            trigger=type(job.trigger).__name__,
            next_run_time=job.next_run_time,
            last_run_time=last_execution.finished_at if last_execution else None,
            last_status=last_execution.status if last_execution else None,
            schedule_description=_format_schedule_description(job),
            enabled=update.enabled if update.enabled is not None else True,
            misfire_grace_time=job.misfire_grace_time,
            max_instances=job.max_instances,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update job {job_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update job: {str(e)}",
        )


@router.post(
    "/jobs/{job_id}/trigger",
    response_model=JobTriggerResponse,
    status_code=status.HTTP_200_OK,
    summary="Manually trigger job",
    description="Triggers immediate execution of a scheduled job",
)
async def trigger_job(job_id: str) -> JobTriggerResponse:
    """Manually trigger a job to run immediately.

    Args:
        job_id: Job ID to trigger

    Returns:
        Trigger confirmation

    Raises:
        HTTPException: If job not found or trigger fails
    """
    try:
        scheduler = get_scheduler_service()
        job = scheduler.get_job(job_id)

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {job_id} not found",
            )

        # Trigger job immediately
        job.modify(next_run_time=datetime.now())
        logger.info(f"Manually triggered job {job_id}")

        return JobTriggerResponse(
            job_id=job_id,
            message=f"Job {job_id} triggered successfully",
            triggered_at=datetime.utcnow(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger job {job_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger job: {str(e)}",
        )


@router.get(
    "/history",
    response_model=JobExecutionHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get job execution history",
    description="Returns execution history for all jobs or a specific job",
)
async def get_execution_history(
    job_id: Optional[str] = Query(None, description="Filter by job ID"),
    job_name: Optional[str] = Query(None, description="Filter by job name"),
    status: Optional[str] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Records per page"),
    db: Session = Depends(get_db),
) -> JobExecutionHistoryResponse:
    """Get job execution history.

    Args:
        job_id: Optional filter by job ID
        job_name: Optional filter by job name
        status: Optional filter by status
        page: Page number (1-based)
        page_size: Number of records per page

    Returns:
        Paginated execution history
    """
    try:
        exec_repo = JobExecutionRepository(db)

        # Calculate offset
        offset = (page - 1) * page_size

        # Get executions
        executions = exec_repo.list_executions(
            job_id=job_id,
            job_name=job_name,
            status=status,
            limit=page_size,
            offset=offset,
        )

        # Get total count
        total = exec_repo.count_executions(
            job_id=job_id,
            job_name=job_name,
            status=status,
        )

        # Convert to response models
        execution_responses = [
            JobExecutionResponse.model_validate(exec) for exec in executions
        ]

        return JobExecutionHistoryResponse(
            executions=execution_responses,
            total=total,
            page=page,
            page_size=page_size,
        )

    except Exception as e:
        logger.error(f"Failed to get execution history: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve execution history: {str(e)}",
        )
