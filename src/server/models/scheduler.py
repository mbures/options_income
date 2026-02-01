"""Pydantic models for scheduler API.

Defines request/response models for scheduler management endpoints,
including job details, execution history, and schedule updates.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class JobInfoResponse(BaseModel):
    """Response model for job information.

    Provides details about a scheduled job including its schedule,
    next/last run times, and current status.

    Attributes:
        id: Job ID
        name: Human-readable job name
        func: Function name being executed
        trigger: Trigger type (interval, cron, etc.)
        next_run_time: Next scheduled execution time
        last_run_time: Last execution time (from history)
        last_status: Status of last execution (success, failure, or None)
        schedule_description: Human-readable schedule description
        enabled: Whether job is currently enabled
        misfire_grace_time: Seconds to allow job to run after scheduled time
        max_instances: Maximum concurrent instances of this job
    """

    id: str
    name: str
    func: str
    trigger: str
    next_run_time: Optional[datetime] = None
    last_run_time: Optional[datetime] = None
    last_status: Optional[str] = None
    schedule_description: str
    enabled: bool = True
    misfire_grace_time: Optional[int] = None
    max_instances: Optional[int] = None

    class Config:
        """Pydantic model configuration."""

        from_attributes = True


class JobListResponse(BaseModel):
    """Response model for listing all jobs.

    Attributes:
        jobs: List of job information
        total: Total number of jobs
    """

    jobs: List[JobInfoResponse]
    total: int


class JobScheduleUpdate(BaseModel):
    """Request model for updating job schedule.

    Attributes:
        trigger: Trigger type (interval or cron)
        schedule_params: Schedule parameters (depends on trigger type)
        enabled: Whether job should be enabled
    """

    trigger: Optional[str] = Field(None, description="Trigger type: interval or cron")
    schedule_params: Optional[Dict[str, Any]] = Field(
        None, description="Schedule parameters (e.g., {'minutes': 5} for interval)"
    )
    enabled: Optional[bool] = Field(None, description="Enable or disable the job")


class JobTriggerResponse(BaseModel):
    """Response model for manual job trigger.

    Attributes:
        job_id: ID of triggered job
        message: Success message
        triggered_at: When the job was triggered
    """

    job_id: str
    message: str
    triggered_at: datetime


class JobExecutionResponse(BaseModel):
    """Response model for job execution history record.

    Attributes:
        id: Execution record ID
        job_id: Job ID
        job_name: Job name
        started_at: Execution start time
        finished_at: Execution finish time
        duration_seconds: Execution duration
        status: Execution status (running, success, failure)
        error_message: Error message if failed
    """

    id: int
    job_id: str
    job_name: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    status: str
    error_message: Optional[str] = None

    class Config:
        """Pydantic model configuration."""

        from_attributes = True


class JobExecutionHistoryResponse(BaseModel):
    """Response model for job execution history list.

    Attributes:
        executions: List of execution records
        total: Total number of records
        page: Current page number
        page_size: Number of records per page
    """

    executions: List[JobExecutionResponse]
    total: int
    page: int = 1
    page_size: int = 50
