"""API endpoints for options recommendations.

This module provides RESTful endpoints for generating trade recommendations
for wheel positions using the RecommendEngine.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.server.database.session import get_db
from src.server.models.recommendation import (
    BatchRecommendationRequest,
    BatchRecommendationResponse,
    RecommendationResponse,
)
from src.server.services.recommendation_service import RecommendationService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["recommendations"])


@router.get(
    "/wheels/{wheel_id}/recommend",
    response_model=RecommendationResponse,
    status_code=status.HTTP_200_OK,
    summary="Get recommendation for wheel",
    description="Generate options recommendation for a wheel position",
)
def get_recommendation(
    wheel_id: int,
    expiration_date: Optional[str] = Query(
        None, description="Target expiration (YYYY-MM-DD)"
    ),
    use_cache: bool = Query(True, description="Use cached recommendations"),
    max_dte: int = Query(14, description="Maximum days to expiration search window", ge=1, le=90),
    db: Session = Depends(get_db),
) -> RecommendationResponse:
    """Generate options recommendation for a wheel position.

    Returns the next recommended trade based on:
    - Current wheel state (cash or shares)
    - Profile (aggressive, moderate, conservative, defensive)
    - Market conditions (volatility, price)
    - Earnings calendar (warns if earnings conflict)

    Args:
        wheel_id: Unique wheel identifier
        expiration_date: Optional target expiration date (YYYY-MM-DD)
        use_cache: Whether to use cached recommendations (default: True)
        db: Database session dependency

    Returns:
        Recommendation response with trade details

    Raises:
        HTTPException: 400 if wheel not found or invalid state
        HTTPException: 500 if recommendation generation fails

    Example:
        >>> GET /api/v1/wheels/1/recommend
        >>> {
        >>>   "wheel_id": 1,
        >>>   "symbol": "AAPL",
        >>>   "direction": "put",
        >>>   "strike": 145.0,
        >>>   "premium_per_share": 2.50
        >>> }
    """
    service = RecommendationService(db)
    try:
        recommendation = service.get_recommendation(
            wheel_id, expiration_date, use_cache, max_dte=max_dte
        )
        logger.info(
            f"Generated recommendation for wheel {wheel_id}: "
            f"{recommendation.direction} @ ${recommendation.strike}"
        )
        return recommendation
    except ValueError as e:
        logger.warning(f"Invalid recommendation request for wheel {wheel_id}: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Recommendation failed for wheel {wheel_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate recommendation",
        )


@router.post(
    "/wheels/recommend/batch",
    response_model=BatchRecommendationResponse,
    status_code=status.HTTP_200_OK,
    summary="Get batch recommendations",
    description="Generate recommendations for multiple symbols",
)
def get_batch_recommendations(
    request: BatchRecommendationRequest,
    db: Session = Depends(get_db),
) -> BatchRecommendationResponse:
    """Generate recommendations for multiple symbols.

    Returns recommendations for all requested symbols, with errors
    for any symbols that fail. Useful for quickly evaluating
    opportunities across multiple positions.

    Args:
        request: Batch recommendation request with symbols and options
        db: Database session dependency

    Returns:
        Batch response with recommendations and errors

    Example:
        >>> POST /api/v1/wheels/recommend/batch
        >>> {
        >>>   "symbols": ["AAPL", "MSFT", "GOOGL"],
        >>>   "expiration_date": "2026-03-21"
        >>> }
        >>> Response:
        >>> {
        >>>   "recommendations": [...],
        >>>   "errors": {"INVALID": "Symbol not found"}
        >>> }
    """
    service = RecommendationService(db)

    recommendations, errors = service.get_batch_recommendations(
        symbols=request.symbols,
        expiration_date=request.expiration_date,
        profile_override=request.profile,
        max_dte=request.max_dte,
    )

    from datetime import datetime

    response = BatchRecommendationResponse(
        recommendations=recommendations,
        errors=errors,
        requested_at=datetime.utcnow(),
    )

    logger.info(
        f"Batch recommendations: {len(recommendations)} successful, "
        f"{len(errors)} errors"
    )
    return response


@router.delete(
    "/wheels/recommend/cache",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear recommendation cache",
    description="Clear all cached recommendations",
)
def clear_recommendation_cache(db: Session = Depends(get_db)):
    """Clear all cached recommendations.

    Useful when market conditions change significantly or after
    extended downtime. Forces fresh recommendations on next request.

    Args:
        db: Database session dependency

    Returns:
        No content (204)

    Example:
        >>> DELETE /api/v1/wheels/recommend/cache
        >>> Status: 204 No Content
    """
    service = RecommendationService(db)
    service.clear_cache()
    logger.info("Recommendation cache cleared")
    return None
