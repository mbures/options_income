"""Wheel API endpoints.

This module provides REST API endpoints for wheel CRUD operations.
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.server.database.session import get_db
from src.server.models.wheel import (
    WheelCreate,
    WheelResponse,
    WheelState,
    WheelUpdate,
)
from src.server.repositories.wheel import WheelRepository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["wheels"])


@router.post(
    "/portfolios/{portfolio_id}/wheels",
    response_model=WheelResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new wheel",
    description="Creates a new wheel position in a portfolio",
)
def create_wheel(
    portfolio_id: str,
    wheel: WheelCreate,
    db: Session = Depends(get_db),
) -> WheelResponse:
    """Create a new wheel in portfolio.

    Args:
        portfolio_id: Parent portfolio identifier
        wheel: Wheel creation data
        db: Database session

    Returns:
        Created wheel data

    Raises:
        HTTPException: If portfolio not found or duplicate wheel exists

    Example:
        >>> POST /api/v1/portfolios/123e4567-e89b-12d3-a456-426614174000/wheels
        >>> {
        >>>     "symbol": "AAPL",
        >>>     "capital_allocated": 10000.0,
        >>>     "profile": "conservative"
        >>> }
    """
    repo = WheelRepository(db)
    try:
        created = repo.create_wheel(portfolio_id, wheel)
        response = WheelResponse.model_validate(created)
        response.trade_count = len(created.trades) if created.trades else 0
        return response
    except ValueError as e:
        logger.warning(f"Failed to create wheel: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(f"Unexpected error creating wheel: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create wheel",
        ) from e


@router.get(
    "/portfolios/{portfolio_id}/wheels",
    response_model=List[WheelResponse],
    summary="List wheels in portfolio",
    description="Retrieves all wheels in a specific portfolio",
)
def list_wheels(
    portfolio_id: str,
    skip: int = 0,
    limit: int = 100,
    active_only: bool = Query(False, description="Only return active wheels"),
    db: Session = Depends(get_db),
) -> List[WheelResponse]:
    """List wheels in portfolio.

    Args:
        portfolio_id: Parent portfolio identifier
        skip: Number of records to skip (pagination)
        limit: Maximum number of records to return
        active_only: If True, only return active wheels
        db: Database session

    Returns:
        List of wheel data

    Example:
        >>> GET /api/v1/portfolios/123e4567-e89b-12d3-a456-426614174000/wheels?active_only=true
    """
    repo = WheelRepository(db)
    wheels = repo.list_wheels_by_portfolio(
        portfolio_id,
        skip=skip,
        limit=limit,
        active_only=active_only,
    )

    # Add trade_count for each wheel
    result = []
    for wheel in wheels:
        response = WheelResponse.model_validate(wheel)
        response.trade_count = len(wheel.trades) if wheel.trades else 0
        result.append(response)

    return result


@router.get(
    "/wheels/{wheel_id}",
    response_model=WheelResponse,
    summary="Get wheel by ID",
    description="Retrieves a specific wheel by its identifier",
)
def get_wheel(
    wheel_id: int,
    db: Session = Depends(get_db),
) -> WheelResponse:
    """Get wheel by ID.

    Args:
        wheel_id: Wheel identifier
        db: Database session

    Returns:
        Wheel data

    Raises:
        HTTPException: If wheel not found

    Example:
        >>> GET /api/v1/wheels/1
    """
    repo = WheelRepository(db)
    wheel = repo.get_wheel(wheel_id)
    if not wheel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wheel not found",
        )

    response = WheelResponse.model_validate(wheel)
    response.trade_count = len(wheel.trades) if wheel.trades else 0
    return response


@router.get(
    "/wheels/{wheel_id}/state",
    response_model=WheelState,
    summary="Get wheel current state",
    description="Retrieves the current state of a wheel including any open trade",
)
def get_wheel_state(
    wheel_id: int,
    db: Session = Depends(get_db),
) -> WheelState:
    """Get wheel current state.

    Args:
        wheel_id: Wheel identifier
        db: Database session

    Returns:
        Wheel state data

    Raises:
        HTTPException: If wheel not found

    Example:
        >>> GET /api/v1/wheels/1/state
    """
    repo = WheelRepository(db)
    state = repo.get_wheel_state(wheel_id)
    if not state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wheel not found",
        )
    return WheelState(**state)


@router.put(
    "/wheels/{wheel_id}",
    response_model=WheelResponse,
    summary="Update wheel",
    description="Updates an existing wheel",
)
def update_wheel(
    wheel_id: int,
    wheel: WheelUpdate,
    db: Session = Depends(get_db),
) -> WheelResponse:
    """Update wheel.

    Args:
        wheel_id: Wheel identifier
        wheel: Wheel update data
        db: Database session

    Returns:
        Updated wheel data

    Raises:
        HTTPException: If wheel not found

    Example:
        >>> PUT /api/v1/wheels/1
        >>> {"capital_allocated": 15000.0, "is_active": true}
    """
    repo = WheelRepository(db)
    updated = repo.update_wheel(wheel_id, wheel)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wheel not found",
        )

    response = WheelResponse.model_validate(updated)
    response.trade_count = len(updated.trades) if updated.trades else 0
    return response


@router.delete(
    "/wheels/{wheel_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete wheel",
    description="Deletes a wheel and all associated trades (cascade)",
)
def delete_wheel(
    wheel_id: int,
    db: Session = Depends(get_db),
) -> None:
    """Delete wheel and all associated trades.

    Args:
        wheel_id: Wheel identifier
        db: Database session

    Raises:
        HTTPException: If wheel not found

    Example:
        >>> DELETE /api/v1/wheels/1
    """
    repo = WheelRepository(db)
    deleted = repo.delete_wheel(wheel_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wheel not found",
        )
