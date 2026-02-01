"""Portfolio API endpoints.

This module provides REST API endpoints for portfolio CRUD operations.
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.server.database.session import get_db
from src.server.models.portfolio import (
    PortfolioCreate,
    PortfolioResponse,
    PortfolioSummary,
    PortfolioUpdate,
)
from src.server.repositories.portfolio import PortfolioRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


@router.post(
    "/",
    response_model=PortfolioResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new portfolio",
    description="Creates a new portfolio for organizing wheel positions",
)
def create_portfolio(
    portfolio: PortfolioCreate,
    db: Session = Depends(get_db),
) -> PortfolioResponse:
    """Create a new portfolio.

    Args:
        portfolio: Portfolio creation data
        db: Database session

    Returns:
        Created portfolio data

    Raises:
        HTTPException: If creation fails

    Example:
        >>> POST /api/v1/portfolios/
        >>> {
        >>>     "name": "Primary Trading",
        >>>     "description": "Main wheel strategy portfolio",
        >>>     "default_capital": 50000.0
        >>> }
    """
    repo = PortfolioRepository(db)
    try:
        created = repo.create_portfolio(portfolio)
        # Add wheel_count for response
        response = PortfolioResponse.model_validate(created)
        response.wheel_count = len(created.wheels) if created.wheels else 0
        return response
    except Exception as e:
        logger.error(f"Failed to create portfolio: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create portfolio",
        ) from e


@router.get(
    "/",
    response_model=List[PortfolioResponse],
    summary="List all portfolios",
    description="Retrieves a paginated list of all portfolios",
)
def list_portfolios(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> List[PortfolioResponse]:
    """List all portfolios.

    Args:
        skip: Number of records to skip (pagination)
        limit: Maximum number of records to return
        db: Database session

    Returns:
        List of portfolio data

    Example:
        >>> GET /api/v1/portfolios/?skip=0&limit=10
    """
    repo = PortfolioRepository(db)
    portfolios = repo.list_portfolios(skip=skip, limit=limit)

    # Add wheel_count for each portfolio
    result = []
    for portfolio in portfolios:
        response = PortfolioResponse.model_validate(portfolio)
        response.wheel_count = len(portfolio.wheels) if portfolio.wheels else 0
        result.append(response)

    return result


@router.get(
    "/{portfolio_id}",
    response_model=PortfolioResponse,
    summary="Get portfolio by ID",
    description="Retrieves a specific portfolio by its identifier",
)
def get_portfolio(
    portfolio_id: str,
    db: Session = Depends(get_db),
) -> PortfolioResponse:
    """Get portfolio by ID.

    Args:
        portfolio_id: Portfolio identifier
        db: Database session

    Returns:
        Portfolio data

    Raises:
        HTTPException: If portfolio not found

    Example:
        >>> GET /api/v1/portfolios/123e4567-e89b-12d3-a456-426614174000
    """
    repo = PortfolioRepository(db)
    portfolio = repo.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found",
        )

    response = PortfolioResponse.model_validate(portfolio)
    response.wheel_count = len(portfolio.wheels) if portfolio.wheels else 0
    return response


@router.get(
    "/{portfolio_id}/summary",
    response_model=PortfolioSummary,
    summary="Get portfolio summary",
    description="Retrieves portfolio data with summary statistics",
)
def get_portfolio_summary(
    portfolio_id: str,
    db: Session = Depends(get_db),
) -> PortfolioSummary:
    """Get portfolio with summary statistics.

    Args:
        portfolio_id: Portfolio identifier
        db: Database session

    Returns:
        Portfolio data with statistics

    Raises:
        HTTPException: If portfolio not found

    Example:
        >>> GET /api/v1/portfolios/123e4567-e89b-12d3-a456-426614174000/summary
    """
    repo = PortfolioRepository(db)
    summary = repo.get_portfolio_summary(portfolio_id)
    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found",
        )
    return PortfolioSummary(**summary)


@router.put(
    "/{portfolio_id}",
    response_model=PortfolioResponse,
    summary="Update portfolio",
    description="Updates an existing portfolio",
)
def update_portfolio(
    portfolio_id: str,
    portfolio: PortfolioUpdate,
    db: Session = Depends(get_db),
) -> PortfolioResponse:
    """Update portfolio.

    Args:
        portfolio_id: Portfolio identifier
        portfolio: Portfolio update data
        db: Database session

    Returns:
        Updated portfolio data

    Raises:
        HTTPException: If portfolio not found

    Example:
        >>> PUT /api/v1/portfolios/123e4567-e89b-12d3-a456-426614174000
        >>> {"name": "Updated Portfolio Name"}
    """
    repo = PortfolioRepository(db)
    updated = repo.update_portfolio(portfolio_id, portfolio)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found",
        )

    response = PortfolioResponse.model_validate(updated)
    response.wheel_count = len(updated.wheels) if updated.wheels else 0
    return response


@router.delete(
    "/{portfolio_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete portfolio",
    description="Deletes a portfolio and all associated wheels (cascade)",
)
def delete_portfolio(
    portfolio_id: str,
    db: Session = Depends(get_db),
) -> None:
    """Delete portfolio and all associated wheels.

    Args:
        portfolio_id: Portfolio identifier
        db: Database session

    Raises:
        HTTPException: If portfolio not found

    Example:
        >>> DELETE /api/v1/portfolios/123e4567-e89b-12d3-a456-426614174000
    """
    repo = PortfolioRepository(db)
    deleted = repo.delete_portfolio(portfolio_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found",
        )
