"""Performance API endpoints.

This module provides REST API endpoints for retrieving wheel
performance metrics including P&L and time-windowed trends.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.server.database.session import get_db
from src.server.models.performance import PerformanceResponse, WheelPerformanceResponse
from src.server.services.performance_service import PerformanceService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["performance"])


@router.get(
    "/performance",
    response_model=PerformanceResponse,
    summary="Get aggregate performance metrics",
    description="Returns combined P&L metrics across all wheels (all-time, 1W, 1M, 1Q)",
)
def get_aggregate_performance(
    db: Session = Depends(get_db),
) -> PerformanceResponse:
    """Get aggregate performance metrics across all wheels.

    Args:
        db: Database session

    Returns:
        PerformanceResponse with aggregate period metrics
    """
    service = PerformanceService(db)
    return service.get_aggregate_performance()


@router.get(
    "/wheels/{wheel_id}/performance",
    response_model=WheelPerformanceResponse,
    summary="Get wheel performance metrics",
    description="Returns P&L metrics for a wheel across time windows (all-time, 1W, 1M, 1Q)",
)
def get_wheel_performance(
    wheel_id: int,
    db: Session = Depends(get_db),
) -> WheelPerformanceResponse:
    """Get performance metrics for a wheel.

    Computes option premium P&L, stock P&L from completed wheel cycles,
    and win rate across all-time, 1-week, 1-month, and 1-quarter windows.

    Args:
        wheel_id: Wheel identifier
        db: Database session

    Returns:
        WheelPerformanceResponse with period metrics

    Raises:
        HTTPException: If wheel not found
    """
    service = PerformanceService(db)
    try:
        return service.get_wheel_performance(wheel_id)
    except ValueError as e:
        logger.warning(f"Performance request failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
