"""API endpoints for position monitoring.

This module provides REST endpoints for monitoring open positions,
including status tracking, risk assessment, and batch operations.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.server.database.session import get_db
from src.server.models.position import (
    BatchPositionResponse,
    PositionStatusResponse,
    RiskAssessmentResponse,
)
from src.server.services.position_service import PositionMonitorService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["positions"])


def get_position_service(db: Session = Depends(get_db)) -> PositionMonitorService:
    """Dependency for position monitor service.

    Args:
        db: Database session

    Returns:
        PositionMonitorService instance
    """
    return PositionMonitorService(db)


@router.get(
    "/wheels/{wheel_id}/position",
    response_model=PositionStatusResponse,
    summary="Get position status",
    description="Get current status for a wheel's open position including moneyness and risk metrics",
)
def get_position_status(
    wheel_id: int,
    force_refresh: bool = Query(
        False, description="Bypass cache and fetch fresh price data"
    ),
    service: PositionMonitorService = Depends(get_position_service),
):
    """Get current status for a wheel's open position.

    Returns detailed position metrics including:
    - Current price and moneyness
    - Days to expiration (calendar and trading)
    - Risk assessment (LOW, MEDIUM, HIGH)
    - ITM/OTM status

    Args:
        wheel_id: Wheel identifier
        force_refresh: Bypass cache for fresh data
        service: Position monitor service

    Returns:
        PositionStatusResponse with current metrics

    Raises:
        HTTPException 404: If wheel not found or has no open position
        HTTPException 500: If status calculation fails
    """
    try:
        return service.get_position_status(wheel_id, force_refresh=force_refresh)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get position status for wheel {wheel_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve position status: {str(e)}",
        )


@router.get(
    "/portfolios/{portfolio_id}/positions",
    response_model=BatchPositionResponse,
    summary="Get portfolio positions",
    description="Get status for all open positions in a portfolio with optional filtering",
)
def get_portfolio_positions(
    portfolio_id: str,
    risk_level: Optional[str] = Query(
        None, description="Filter by risk level (LOW, MEDIUM, HIGH)"
    ),
    min_dte: Optional[int] = Query(None, description="Minimum days to expiration", ge=0),
    max_dte: Optional[int] = Query(None, description="Maximum days to expiration", ge=0),
    force_refresh: bool = Query(
        False, description="Bypass cache and fetch fresh price data"
    ),
    service: PositionMonitorService = Depends(get_position_service),
):
    """Get status for all open positions in a portfolio.

    Supports filtering by:
    - Risk level (LOW, MEDIUM, HIGH)
    - Days to expiration range

    Returns summary view with risk counts for the portfolio.

    Args:
        portfolio_id: Portfolio identifier
        risk_level: Optional filter by risk level
        min_dte: Optional minimum days to expiration
        max_dte: Optional maximum days to expiration
        force_refresh: Bypass cache for fresh data
        service: Position monitor service

    Returns:
        BatchPositionResponse with matching positions and risk counts

    Raises:
        HTTPException 422: If risk_level is invalid
        HTTPException 500: If batch retrieval fails
    """
    # Validate risk level
    if risk_level and risk_level not in ["LOW", "MEDIUM", "HIGH"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="risk_level must be one of: LOW, MEDIUM, HIGH",
        )

    # Validate DTE range
    if min_dte is not None and max_dte is not None and min_dte > max_dte:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="min_dte cannot be greater than max_dte",
        )

    try:
        return service.get_portfolio_positions(
            portfolio_id,
            risk_level=risk_level,
            min_dte=min_dte,
            max_dte=max_dte,
            force_refresh=force_refresh,
        )
    except Exception as e:
        logger.error(f"Failed to get portfolio positions for {portfolio_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve portfolio positions: {str(e)}",
        )


@router.get(
    "/positions/open",
    response_model=BatchPositionResponse,
    summary="Get all open positions",
    description="Get status for all open positions across all portfolios with optional filtering",
)
def get_all_open_positions(
    risk_level: Optional[str] = Query(
        None, description="Filter by risk level (LOW, MEDIUM, HIGH)"
    ),
    min_dte: Optional[int] = Query(None, description="Minimum days to expiration", ge=0),
    max_dte: Optional[int] = Query(None, description="Maximum days to expiration", ge=0),
    force_refresh: bool = Query(
        False, description="Bypass cache and fetch fresh price data"
    ),
    service: PositionMonitorService = Depends(get_position_service),
):
    """Get status for all open positions across all portfolios.

    Supports filtering by:
    - Risk level (LOW, MEDIUM, HIGH)
    - Days to expiration range

    Useful for system-wide monitoring and risk oversight.

    Args:
        risk_level: Optional filter by risk level
        min_dte: Optional minimum days to expiration
        max_dte: Optional maximum days to expiration
        force_refresh: Bypass cache for fresh data
        service: Position monitor service

    Returns:
        BatchPositionResponse with matching positions and risk counts

    Raises:
        HTTPException 422: If risk_level is invalid
        HTTPException 500: If batch retrieval fails
    """
    # Validate risk level
    if risk_level and risk_level not in ["LOW", "MEDIUM", "HIGH"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="risk_level must be one of: LOW, MEDIUM, HIGH",
        )

    # Validate DTE range
    if min_dte is not None and max_dte is not None and min_dte > max_dte:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="min_dte cannot be greater than max_dte",
        )

    try:
        return service.get_all_open_positions(
            risk_level=risk_level,
            min_dte=min_dte,
            max_dte=max_dte,
            force_refresh=force_refresh,
        )
    except Exception as e:
        logger.error(f"Failed to get all open positions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve open positions: {str(e)}",
        )


@router.get(
    "/wheels/{wheel_id}/risk",
    response_model=RiskAssessmentResponse,
    summary="Get risk assessment",
    description="Get focused risk assessment for a wheel's open position",
)
def get_risk_assessment(
    wheel_id: int,
    force_refresh: bool = Query(
        False, description="Bypass cache and fetch fresh price data"
    ),
    service: PositionMonitorService = Depends(get_position_service),
):
    """Get focused risk assessment for a wheel's open position.

    Provides a simplified, risk-focused view including:
    - Risk level and icon
    - ITM/OTM status
    - Moneyness percentage
    - Days to expiration

    Useful for quick risk checks and alerts.

    Args:
        wheel_id: Wheel identifier
        force_refresh: Bypass cache for fresh data
        service: Position monitor service

    Returns:
        RiskAssessmentResponse with risk-focused metrics

    Raises:
        HTTPException 404: If wheel not found or has no open position
        HTTPException 500: If risk assessment fails
    """
    try:
        return service.get_risk_assessment(wheel_id, force_refresh=force_refresh)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get risk assessment for wheel {wheel_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve risk assessment: {str(e)}",
        )
