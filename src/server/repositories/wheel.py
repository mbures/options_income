"""Repository for wheel data access operations.

This module provides data access methods for wheel CRUD operations,
including querying, creating, updating, and deleting wheels.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from src.server.database.models.portfolio import Portfolio
from src.server.database.models.trade import Trade
from src.server.database.models.wheel import Wheel
from src.server.models.wheel import WheelCreate, WheelUpdate

logger = logging.getLogger(__name__)


class WheelRepository:
    """Repository for wheel data access.

    Handles all database operations related to wheels, including
    CRUD operations and state queries.

    Attributes:
        db: SQLAlchemy database session
    """

    def __init__(self, db: Session):
        """Initialize wheel repository.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def create_wheel(self, portfolio_id: str, wheel_data: WheelCreate) -> Wheel:
        """Create a new wheel in portfolio.

        Args:
            portfolio_id: Parent portfolio identifier
            wheel_data: Wheel creation data

        Returns:
            Created wheel instance

        Raises:
            ValueError: If portfolio doesn't exist or duplicate wheel exists

        Example:
            >>> repo = WheelRepository(db)
            >>> wheel = repo.create_wheel(
            >>>     "123e4567-e89b-12d3-a456-426614174000",
            >>>     WheelCreate(symbol="AAPL", capital_allocated=10000.0, profile="conservative")
            >>> )
        """
        # Validate portfolio exists
        portfolio = (
            self.db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
        )
        if not portfolio:
            raise ValueError(f"Portfolio not found: {portfolio_id}")

        # Check for duplicate (portfolio_id, symbol)
        existing = (
            self.db.query(Wheel)
            .filter(
                and_(
                    Wheel.portfolio_id == portfolio_id,
                    Wheel.symbol == wheel_data.symbol,
                )
            )
            .first()
        )
        if existing:
            raise ValueError(
                f"Wheel for {wheel_data.symbol} already exists in portfolio {portfolio_id}"
            )

        # Create Wheel instance with initial state
        wheel = Wheel(
            portfolio_id=portfolio_id,
            symbol=wheel_data.symbol,
            capital_allocated=wheel_data.capital_allocated,
            profile=wheel_data.profile,
            state="cash",
            shares_held=0,
            is_active=True,
        )

        # Add to session, commit, and refresh
        try:
            self.db.add(wheel)
            self.db.commit()
            self.db.refresh(wheel)
            logger.info(
                f"Created wheel: {wheel.id} - {wheel.symbol} in portfolio {portfolio_id}"
            )
            return wheel
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"IntegrityError creating wheel: {e}")
            raise ValueError(f"Failed to create wheel: constraint violation") from e

    def get_wheel(self, wheel_id: int) -> Optional[Wheel]:
        """Get wheel by ID.

        Args:
            wheel_id: Wheel identifier

        Returns:
            Wheel instance if found, None otherwise

        Example:
            >>> repo = WheelRepository(db)
            >>> wheel = repo.get_wheel(1)
        """
        wheel = self.db.query(Wheel).filter(Wheel.id == wheel_id).first()
        return wheel

    def list_wheels_by_portfolio(
        self,
        portfolio_id: str,
        skip: int = 0,
        limit: int = 100,
        active_only: bool = False,
    ) -> List[Wheel]:
        """List wheels in a portfolio.

        Args:
            portfolio_id: Parent portfolio identifier
            skip: Number of records to skip
            limit: Maximum number of records to return
            active_only: If True, only return active wheels

        Returns:
            List of wheel instances

        Example:
            >>> repo = WheelRepository(db)
            >>> wheels = repo.list_wheels_by_portfolio(
            >>>     "123e4567-e89b-12d3-a456-426614174000",
            >>>     active_only=True
            >>> )
        """
        query = self.db.query(Wheel).filter(Wheel.portfolio_id == portfolio_id)

        if active_only:
            query = query.filter(Wheel.is_active == True)

        wheels = query.order_by(Wheel.symbol).offset(skip).limit(limit).all()
        return wheels

    def update_wheel(self, wheel_id: int, wheel_data: WheelUpdate) -> Optional[Wheel]:
        """Update wheel.

        Only updates fields that are provided (not None) in wheel_data.

        Args:
            wheel_id: Wheel identifier
            wheel_data: Wheel update data

        Returns:
            Updated wheel instance if found, None otherwise

        Example:
            >>> repo = WheelRepository(db)
            >>> wheel = repo.update_wheel(
            >>>     1,
            >>>     WheelUpdate(capital_allocated=15000.0)
            >>> )
        """
        # Get wheel
        wheel = self.get_wheel(wheel_id)
        if not wheel:
            return None

        # Update only provided fields
        update_data = wheel_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(wheel, field, value)

        # Update timestamp
        wheel.updated_at = datetime.utcnow()

        # Commit and refresh
        self.db.commit()
        self.db.refresh(wheel)

        logger.info(f"Updated wheel: {wheel.id} - {wheel.symbol}")
        return wheel

    def delete_wheel(self, wheel_id: int) -> bool:
        """Delete wheel (cascades to trades, snapshots).

        Deletes the wheel and all associated trades and snapshots due to cascade rules.

        Args:
            wheel_id: Wheel identifier

        Returns:
            True if wheel was deleted, False if not found

        Example:
            >>> repo = WheelRepository(db)
            >>> deleted = repo.delete_wheel(1)
        """
        # Get wheel
        wheel = self.get_wheel(wheel_id)
        if not wheel:
            return False

        # Delete from session
        self.db.delete(wheel)
        self.db.commit()

        logger.info(f"Deleted wheel: {wheel_id}")
        return True

    def get_wheel_state(self, wheel_id: int) -> Optional[Dict]:
        """Get wheel with current state info.

        Retrieves wheel data along with any currently open trade.

        Args:
            wheel_id: Wheel identifier

        Returns:
            Dictionary with wheel state data, or None if not found

        Example:
            >>> repo = WheelRepository(db)
            >>> state = repo.get_wheel_state(1)
            >>> print(state["state"])
        """
        # Get wheel with trades joined
        wheel = (
            self.db.query(Wheel)
            .options(joinedload(Wheel.trades))
            .filter(Wheel.id == wheel_id)
            .first()
        )

        if not wheel:
            return None

        # Find open trade if exists
        open_trade = None
        if wheel.trades:
            for trade in wheel.trades:
                if trade.closed_at is None:
                    open_trade = {
                        "id": trade.id,
                        "option_type": trade.direction,
                        "strike": trade.strike,
                        "expiration": trade.expiration_date,
                        "quantity": trade.contracts,
                        "premium": trade.total_premium,
                        "opened_at": (
                            trade.opened_at.isoformat() if trade.opened_at else None
                        ),
                    }
                    break

        # Return dictionary with wheel and open trade
        return {
            "id": wheel.id,
            "symbol": wheel.symbol,
            "state": wheel.state,
            "shares_held": wheel.shares_held,
            "cost_basis": wheel.cost_basis,
            "open_trade": open_trade,
        }
