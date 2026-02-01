"""API v1 router with core endpoints.

This module provides version 1 of the API with system information
and health check endpoints.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, status

from src.server.api.v1 import (
    portfolios,
    positions,
    recommendations,
    scheduler,
    trades,
    wheels,
)
from src.server.config import settings
from src.server.database.session import check_database_connection
from src.server.models.common import InfoResponse

logger = logging.getLogger(__name__)

# Create v1 router
router = APIRouter(
    prefix="/api/v1",
    tags=["v1"],
)

# Include sub-routers
router.include_router(portfolios.router)
router.include_router(wheels.router)
router.include_router(trades.router)
router.include_router(recommendations.router)
router.include_router(positions.router)
router.include_router(scheduler.router)


@router.get(
    "/info",
    response_model=InfoResponse,
    status_code=status.HTTP_200_OK,
    summary="Get system information",
    description="Returns system information including version and database status",
)
async def get_info() -> InfoResponse:
    """Get system information endpoint.

    Returns application name, version, status, and database connectivity.

    Returns:
        System information including database connection status

    Example:
        >>> GET /api/v1/info
        >>> {
        >>>     "app_name": "Wheel Strategy API",
        >>>     "version": "1.0.0",
        >>>     "status": "running",
        >>>     "database_connected": true,
        >>>     "timestamp": "2026-01-31T10:00:00"
        >>> }
    """
    db_connected = check_database_connection()

    return InfoResponse(
        app_name=settings.app_name,
        version=settings.version,
        status="running",
        database_connected=db_connected,
        timestamp=datetime.utcnow(),
    )
