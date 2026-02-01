"""Common Pydantic models for API requests and responses.

This module contains shared response models used across the API.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response model.

    Attributes:
        status: Service health status
        timestamp: Current server timestamp
        scheduler_running: Whether background scheduler is running
    """

    status: str = Field(default="healthy", description="Service health status")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Current server timestamp"
    )
    scheduler_running: Optional[bool] = Field(
        default=None, description="Whether background scheduler is running"
    )


class InfoResponse(BaseModel):
    """System information response model.

    Attributes:
        app_name: Application name
        version: Application version
        status: Service status
        database_connected: Whether database connection is working
        timestamp: Current server timestamp
    """

    app_name: str = Field(..., description="Application name")
    version: str = Field(..., description="Application version")
    status: str = Field(default="running", description="Service status")
    database_connected: bool = Field(
        ..., description="Database connection status"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Current server timestamp"
    )


class ErrorResponse(BaseModel):
    """Standard error response model.

    Attributes:
        error: Error type or code
        message: Human-readable error message
        detail: Additional error details
        timestamp: When the error occurred
    """

    error: str = Field(..., description="Error type or code")
    message: str = Field(..., description="Human-readable error message")
    detail: Optional[Any] = Field(
        default=None, description="Additional error details"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Error timestamp"
    )
