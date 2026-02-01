"""Trade API endpoints.

This module provides REST API endpoints for trade operations,
including recording trades, managing expirations, and early closes.
"""

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.server.database.session import get_db
from src.server.models.trade import (
    TradeCloseRequest,
    TradeCreate,
    TradeExpireRequest,
    TradeResponse,
    TradeUpdate,
)
from src.server.repositories.trade import TradeRepository
from src.server.services.wheel_service import WheelService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["trades"])


@router.post(
    "/wheels/{wheel_id}/trades",
    response_model=TradeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a new trade",
    description="Records a new option trade for a wheel with state machine validation",
)
def create_trade(
    wheel_id: int,
    trade: TradeCreate,
    db: Session = Depends(get_db),
) -> TradeResponse:
    """Record a new option trade for a wheel.

    Validates wheel state allows this trade direction (puts from CASH,
    calls from SHARES) and creates the trade, transitioning wheel state.

    Args:
        wheel_id: Parent wheel identifier
        trade: Trade creation data
        db: Database session

    Returns:
        Created trade data

    Raises:
        HTTPException: If wheel not found, invalid state, or insufficient capital/shares

    Example:
        >>> POST /api/v1/wheels/1/trades
        >>> {
        >>>     "direction": "put",
        >>>     "strike": 150.0,
        >>>     "expiration_date": "2026-03-20",
        >>>     "premium_per_share": 2.50,
        >>>     "contracts": 1
        >>> }
    """
    service = WheelService(db)
    try:
        created_trade = service.record_trade(wheel_id, trade)
        return TradeResponse.model_validate(created_trade)
    except ValueError as e:
        logger.warning(f"Failed to create trade: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(f"Unexpected error creating trade: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create trade",
        ) from e


@router.get(
    "/wheels/{wheel_id}/trades",
    response_model=list[TradeResponse],
    summary="List trades for wheel",
    description="Retrieves all trades for a specific wheel with optional filtering",
)
def list_wheel_trades(
    wheel_id: int,
    skip: int = 0,
    limit: int = 100,
    outcome: Optional[str] = Query(None, description="Filter by outcome (open, expired_assigned, etc.)"),
    db: Session = Depends(get_db),
) -> list[TradeResponse]:
    """List all trades for a wheel.

    Args:
        wheel_id: Parent wheel identifier
        skip: Number of records to skip (pagination)
        limit: Maximum number of records to return
        outcome: Filter by outcome if provided
        db: Database session

    Returns:
        List of trade data ordered by opened_at descending

    Example:
        >>> GET /api/v1/wheels/1/trades?outcome=open
    """
    repo = TradeRepository(db)
    trades = repo.list_trades_by_wheel(wheel_id, skip=skip, limit=limit, outcome=outcome)
    return [TradeResponse.model_validate(t) for t in trades]


@router.get(
    "/trades",
    response_model=list[TradeResponse],
    summary="List all trades",
    description="Retrieves all trades across all wheels with optional filtering",
)
def list_all_trades(
    skip: int = 0,
    limit: int = 100,
    outcome: Optional[str] = Query(None, description="Filter by outcome"),
    from_date: Optional[date] = Query(None, description="Filter trades from this date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="Filter trades to this date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
) -> list[TradeResponse]:
    """List all trades with filtering.

    Args:
        skip: Number of records to skip (pagination)
        limit: Maximum number of records to return
        outcome: Filter by outcome if provided
        from_date: Filter trades opened on or after this date
        to_date: Filter trades opened on or before this date
        db: Database session

    Returns:
        List of trade data ordered by opened_at descending

    Example:
        >>> GET /api/v1/trades?outcome=open&from_date=2026-01-01
    """
    repo = TradeRepository(db)
    trades = repo.list_trades(
        skip=skip,
        limit=limit,
        outcome=outcome,
        from_date=from_date,
        to_date=to_date,
    )
    return [TradeResponse.model_validate(t) for t in trades]


@router.get(
    "/trades/{trade_id}",
    response_model=TradeResponse,
    summary="Get trade by ID",
    description="Retrieves a specific trade by identifier",
)
def get_trade(
    trade_id: int,
    db: Session = Depends(get_db),
) -> TradeResponse:
    """Get trade by ID.

    Args:
        trade_id: Trade identifier
        db: Database session

    Returns:
        Trade data

    Raises:
        HTTPException: If trade not found

    Example:
        >>> GET /api/v1/trades/1
    """
    repo = TradeRepository(db)
    trade = repo.get_trade(trade_id)
    if not trade:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trade not found: {trade_id}",
        )
    return TradeResponse.model_validate(trade)


@router.put(
    "/trades/{trade_id}",
    response_model=TradeResponse,
    summary="Update trade details",
    description="Updates trade details (premium, contracts, etc.)",
)
def update_trade(
    trade_id: int,
    trade: TradeUpdate,
    db: Session = Depends(get_db),
) -> TradeResponse:
    """Update trade details.

    Only updates fields that are provided in the request.

    Args:
        trade_id: Trade identifier
        trade: Trade update data
        db: Database session

    Returns:
        Updated trade data

    Raises:
        HTTPException: If trade not found

    Example:
        >>> PUT /api/v1/trades/1
        >>> {
        >>>     "premium_per_share": 2.75
        >>> }
    """
    repo = TradeRepository(db)
    updated = repo.update_trade(trade_id, trade)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trade not found: {trade_id}",
        )
    return TradeResponse.model_validate(updated)


@router.delete(
    "/trades/{trade_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete trade",
    description="Deletes a trade record",
)
def delete_trade(
    trade_id: int,
    db: Session = Depends(get_db),
) -> None:
    """Delete trade.

    Args:
        trade_id: Trade identifier
        db: Database session

    Raises:
        HTTPException: If trade not found

    Example:
        >>> DELETE /api/v1/trades/1
    """
    repo = TradeRepository(db)
    deleted = repo.delete_trade(trade_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trade not found: {trade_id}",
        )


@router.post(
    "/trades/{trade_id}/expire",
    response_model=TradeResponse,
    summary="Record trade expiration",
    description="Records expiration outcome based on stock price at expiration",
)
def expire_trade(
    trade_id: int,
    request: TradeExpireRequest,
    db: Session = Depends(get_db),
) -> TradeResponse:
    """Record trade expiration outcome.

    Determines if option expired worthless or was assigned based on
    price_at_expiry vs strike. Updates trade outcome and wheel state.

    For puts: assigned if price <= strike
    For calls: assigned if price >= strike

    Args:
        trade_id: Trade identifier
        request: Expiration request with price_at_expiry
        db: Database session

    Returns:
        Updated trade data with outcome

    Raises:
        HTTPException: If trade not found, not open, or invalid state

    Example:
        >>> POST /api/v1/trades/1/expire
        >>> {
        >>>     "price_at_expiry": 148.50
        >>> }
    """
    service = WheelService(db)
    try:
        updated_trade = service.expire_trade(trade_id, request)
        return TradeResponse.model_validate(updated_trade)
    except ValueError as e:
        logger.warning(f"Failed to expire trade: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(f"Unexpected error expiring trade: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to expire trade",
        ) from e


@router.post(
    "/trades/{trade_id}/close",
    response_model=TradeResponse,
    summary="Close trade early",
    description="Closes trade before expiration by buying back the option",
)
def close_trade_early(
    trade_id: int,
    request: TradeCloseRequest,
    db: Session = Depends(get_db),
) -> TradeResponse:
    """Close trade before expiration.

    Buys back the option early and transitions wheel state back to
    base state (CASH or SHARES).

    Args:
        trade_id: Trade identifier
        request: Close request with close_price
        db: Database session

    Returns:
        Updated trade data with outcome

    Raises:
        HTTPException: If trade not found, not open, or invalid state

    Example:
        >>> POST /api/v1/trades/1/close
        >>> {
        >>>     "close_price": 1.25
        >>> }
    """
    service = WheelService(db)
    try:
        updated_trade = service.close_trade_early(trade_id, request)
        return TradeResponse.model_validate(updated_trade)
    except ValueError as e:
        logger.warning(f"Failed to close trade early: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(f"Unexpected error closing trade: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to close trade",
        ) from e
