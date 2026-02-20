"""API endpoints for watchlist management and opportunity scanning.

Provides CRUD for watchlist symbols, opportunity retrieval with filters,
and manual scan triggering.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.server.database.session import get_db
from src.server.models.watchlist import (
    OpportunityCountResponse,
    OpportunityResponse,
    ScanResultResponse,
    WatchlistItemCreate,
    WatchlistItemResponse,
)
from src.server.services.watchlist_service import WatchlistService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["watchlist"])


@router.get(
    "/watchlist",
    response_model=List[WatchlistItemResponse],
    status_code=status.HTTP_200_OK,
    summary="List watchlist symbols",
)
def list_watchlist(db: Session = Depends(get_db)) -> List[WatchlistItemResponse]:
    """List all symbols on the watchlist."""
    service = WatchlistService(db)
    return service.list_watchlist()


@router.post(
    "/watchlist",
    response_model=WatchlistItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add symbol to watchlist",
)
def add_to_watchlist(
    item: WatchlistItemCreate,
    db: Session = Depends(get_db),
) -> WatchlistItemResponse:
    """Add a symbol to the watchlist for opportunity scanning."""
    service = WatchlistService(db)
    try:
        return service.add_symbol(item.symbol, item.notes)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(e)
        )


@router.delete(
    "/watchlist/{symbol}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove symbol from watchlist",
)
def remove_from_watchlist(
    symbol: str,
    db: Session = Depends(get_db),
):
    """Remove a symbol from the watchlist and its opportunities."""
    service = WatchlistService(db)
    removed = service.remove_symbol(symbol)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{symbol.upper()} not found on watchlist",
        )
    return None


@router.get(
    "/opportunities",
    response_model=List[OpportunityResponse],
    status_code=status.HTTP_200_OK,
    summary="List opportunities",
)
def list_opportunities(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    direction: Optional[str] = Query(None, description="Filter by direction (put/call)"),
    profile: Optional[str] = Query(None, description="Filter by profile"),
    unread_only: bool = Query(False, description="Only show unread"),
    limit: int = Query(100, ge=1, le=500, description="Max results"),
    db: Session = Depends(get_db),
) -> List[OpportunityResponse]:
    """List scanned opportunities with optional filters."""
    service = WatchlistService(db)
    return service.get_opportunities(
        symbol=symbol,
        direction=direction,
        profile=profile,
        unread_only=unread_only,
        limit=limit,
    )


@router.get(
    "/opportunities/count",
    response_model=OpportunityCountResponse,
    status_code=status.HTTP_200_OK,
    summary="Get unread opportunity count",
)
def get_opportunity_count(
    db: Session = Depends(get_db),
) -> OpportunityCountResponse:
    """Get count of unread opportunities (for badge display)."""
    service = WatchlistService(db)
    return OpportunityCountResponse(unread_count=service.get_unread_count())


@router.post(
    "/opportunities/{opportunity_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark opportunity as read",
)
def mark_opportunity_read(
    opportunity_id: int,
    db: Session = Depends(get_db),
):
    """Mark a single opportunity as read."""
    service = WatchlistService(db)
    found = service.mark_read(opportunity_id)
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Opportunity {opportunity_id} not found",
        )
    return None


@router.post(
    "/opportunities/read-all",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark all opportunities as read",
)
def mark_all_opportunities_read(
    db: Session = Depends(get_db),
):
    """Mark all opportunities as read."""
    service = WatchlistService(db)
    service.mark_all_read()
    return None


@router.post(
    "/watchlist/scan",
    response_model=ScanResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger manual scan",
)
def trigger_scan(
    db: Session = Depends(get_db),
) -> ScanResultResponse:
    """Trigger a manual scan of all watchlist symbols."""
    service = WatchlistService(db)
    try:
        result = service.scan_all()
        return ScanResultResponse(**result)
    except Exception as e:
        logger.error(f"Manual scan failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Scan failed",
        )
