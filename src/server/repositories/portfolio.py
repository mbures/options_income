"""Repository for portfolio data access operations.

This module provides data access methods for portfolio CRUD operations,
including querying, creating, updating, and deleting portfolios.
"""

import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.server.database.models.portfolio import Portfolio
from src.server.database.models.wheel import Wheel
from src.server.models.portfolio import PortfolioCreate, PortfolioUpdate

logger = logging.getLogger(__name__)


class PortfolioRepository:
    """Repository for portfolio data access.

    Handles all database operations related to portfolios, including
    CRUD operations and summary statistics.

    Attributes:
        db: SQLAlchemy database session
    """

    def __init__(self, db: Session):
        """Initialize portfolio repository.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def create_portfolio(self, portfolio_data: PortfolioCreate) -> Portfolio:
        """Create a new portfolio.

        Args:
            portfolio_data: Portfolio creation data

        Returns:
            Created portfolio instance

        Raises:
            Exception: If database operation fails

        Example:
            >>> repo = PortfolioRepository(db)
            >>> portfolio = repo.create_portfolio(
            >>>     PortfolioCreate(name="Test Portfolio", default_capital=10000.0)
            >>> )
        """
        # Generate UUID for portfolio ID
        portfolio_id = str(uuid.uuid4())

        # Create Portfolio model instance
        portfolio = Portfolio(
            id=portfolio_id,
            name=portfolio_data.name,
            description=portfolio_data.description,
            default_capital=portfolio_data.default_capital,
        )

        # Add to session, commit, and refresh
        self.db.add(portfolio)
        self.db.commit()
        self.db.refresh(portfolio)

        logger.info(f"Created portfolio: {portfolio.id} - {portfolio.name}")
        return portfolio

    def get_portfolio(self, portfolio_id: str) -> Optional[Portfolio]:
        """Get portfolio by ID.

        Args:
            portfolio_id: Portfolio identifier

        Returns:
            Portfolio instance if found, None otherwise

        Example:
            >>> repo = PortfolioRepository(db)
            >>> portfolio = repo.get_portfolio("123e4567-e89b-12d3-a456-426614174000")
        """
        portfolio = (
            self.db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
        )
        return portfolio

    def list_portfolios(self, skip: int = 0, limit: int = 100) -> List[Portfolio]:
        """List all portfolios with pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of portfolio instances

        Example:
            >>> repo = PortfolioRepository(db)
            >>> portfolios = repo.list_portfolios(skip=0, limit=10)
        """
        portfolios = (
            self.db.query(Portfolio)
            .order_by(Portfolio.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return portfolios

    def update_portfolio(
        self, portfolio_id: str, portfolio_data: PortfolioUpdate
    ) -> Optional[Portfolio]:
        """Update portfolio.

        Only updates fields that are provided (not None) in portfolio_data.

        Args:
            portfolio_id: Portfolio identifier
            portfolio_data: Portfolio update data

        Returns:
            Updated portfolio instance if found, None otherwise

        Example:
            >>> repo = PortfolioRepository(db)
            >>> portfolio = repo.update_portfolio(
            >>>     "123e4567-e89b-12d3-a456-426614174000",
            >>>     PortfolioUpdate(name="Updated Name")
            >>> )
        """
        # Get portfolio
        portfolio = self.get_portfolio(portfolio_id)
        if not portfolio:
            return None

        # Update only provided fields
        update_data = portfolio_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(portfolio, field, value)

        # Update timestamp
        portfolio.updated_at = datetime.utcnow()

        # Commit and refresh
        self.db.commit()
        self.db.refresh(portfolio)

        logger.info(f"Updated portfolio: {portfolio.id} - {portfolio.name}")
        return portfolio

    def delete_portfolio(self, portfolio_id: str) -> bool:
        """Delete portfolio (cascades to wheels).

        Deletes the portfolio and all associated wheels due to cascade rules.

        Args:
            portfolio_id: Portfolio identifier

        Returns:
            True if portfolio was deleted, False if not found

        Example:
            >>> repo = PortfolioRepository(db)
            >>> deleted = repo.delete_portfolio("123e4567-e89b-12d3-a456-426614174000")
        """
        # Get portfolio
        portfolio = self.get_portfolio(portfolio_id)
        if not portfolio:
            return False

        # Delete from session
        self.db.delete(portfolio)
        self.db.commit()

        logger.info(f"Deleted portfolio: {portfolio_id}")
        return True

    def get_portfolio_summary(self, portfolio_id: str) -> Optional[Dict]:
        """Get portfolio with summary statistics.

        Retrieves portfolio data along with computed statistics about
        wheels and capital allocation.

        Args:
            portfolio_id: Portfolio identifier

        Returns:
            Dictionary with portfolio data and statistics, or None if not found

        Example:
            >>> repo = PortfolioRepository(db)
            >>> summary = repo.get_portfolio_summary("123e4567-e89b-12d3-a456-426614174000")
            >>> print(summary["total_wheels"])
        """
        # Get portfolio
        portfolio = self.get_portfolio(portfolio_id)
        if not portfolio:
            return None

        # Calculate statistics
        total_wheels = (
            self.db.query(func.count(Wheel.id))
            .filter(Wheel.portfolio_id == portfolio_id)
            .scalar()
            or 0
        )

        active_wheels = (
            self.db.query(func.count(Wheel.id))
            .filter(Wheel.portfolio_id == portfolio_id, Wheel.is_active == True)
            .scalar()
            or 0
        )

        total_capital = (
            self.db.query(func.sum(Wheel.capital_allocated))
            .filter(Wheel.portfolio_id == portfolio_id)
            .scalar()
            or 0.0
        )

        # Calculate total positions value (shares_held * cost_basis)
        wheels_with_shares = (
            self.db.query(Wheel)
            .filter(
                Wheel.portfolio_id == portfolio_id,
                Wheel.shares_held > 0,
                Wheel.cost_basis.isnot(None),
            )
            .all()
        )

        total_positions_value = sum(
            wheel.shares_held * wheel.cost_basis for wheel in wheels_with_shares
        )

        # Return dictionary with portfolio and stats
        return {
            "id": portfolio.id,
            "name": portfolio.name,
            "description": portfolio.description,
            "default_capital": portfolio.default_capital,
            "created_at": portfolio.created_at,
            "updated_at": portfolio.updated_at,
            "wheel_count": total_wheels,
            "total_wheels": total_wheels,
            "active_wheels": active_wheels,
            "total_capital_allocated": float(total_capital),
            "total_positions_value": float(total_positions_value),
        }
