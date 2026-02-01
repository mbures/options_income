"""Repository for trade data access operations.

This module provides data access methods for trade CRUD operations,
including querying, creating, updating, and managing trade outcomes.
"""

import logging
from datetime import date, datetime
from typing import Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session, joinedload

from src.server.database.models.trade import Trade
from src.server.database.models.wheel import Wheel
from src.server.models.trade import TradeCreate, TradeUpdate

logger = logging.getLogger(__name__)


class TradeRepository:
    """Repository for trade data access.

    Handles all database operations related to trades, including
    CRUD operations, expiration handling, and early closes.

    Attributes:
        db: SQLAlchemy database session
    """

    def __init__(self, db: Session):
        """Initialize trade repository.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def create_trade(self, wheel_id: int, trade_data: TradeCreate) -> Trade:
        """Create a new trade for a wheel.

        Args:
            wheel_id: Parent wheel identifier
            trade_data: Trade creation data

        Returns:
            Created trade instance

        Raises:
            ValueError: If wheel doesn't exist

        Example:
            >>> repo = TradeRepository(db)
            >>> trade = repo.create_trade(
            >>>     1,
            >>>     TradeCreate(direction="put", strike=150.0, ...)
            >>> )
        """
        # Validate wheel exists
        wheel = self.db.query(Wheel).filter(Wheel.id == wheel_id).first()
        if not wheel:
            raise ValueError(f"Wheel not found: {wheel_id}")

        # Calculate total premium (premium per share * contracts * 100 shares)
        total_premium = trade_data.premium_per_share * trade_data.contracts * 100

        # Create Trade instance
        trade = Trade(
            wheel_id=wheel_id,
            symbol=wheel.symbol,
            direction=trade_data.direction,
            strike=trade_data.strike,
            expiration_date=trade_data.expiration_date,
            premium_per_share=trade_data.premium_per_share,
            contracts=trade_data.contracts,
            total_premium=total_premium,
            outcome="open",
            opened_at=datetime.utcnow(),
        )

        # Add to session, commit, refresh
        self.db.add(trade)
        self.db.commit()
        self.db.refresh(trade)

        logger.info(
            f"Created trade: {trade.id} - {trade.symbol} {trade.direction} "
            f"${trade.strike} x {trade.contracts} contracts"
        )
        return trade

    def get_trade(self, trade_id: int) -> Optional[Trade]:
        """Get trade by ID.

        Args:
            trade_id: Trade identifier

        Returns:
            Trade instance if found, None otherwise

        Example:
            >>> repo = TradeRepository(db)
            >>> trade = repo.get_trade(1)
        """
        trade = (
            self.db.query(Trade)
            .options(joinedload(Trade.wheel))
            .filter(Trade.id == trade_id)
            .first()
        )
        return trade

    def list_trades_by_wheel(
        self,
        wheel_id: int,
        skip: int = 0,
        limit: int = 100,
        outcome: Optional[str] = None,
    ) -> list[Trade]:
        """List trades for a wheel with optional filtering.

        Args:
            wheel_id: Parent wheel identifier
            skip: Number of records to skip (pagination)
            limit: Maximum number of records to return
            outcome: Filter by outcome if provided

        Returns:
            List of trade instances

        Example:
            >>> repo = TradeRepository(db)
            >>> trades = repo.list_trades_by_wheel(1, outcome="open")
        """
        query = self.db.query(Trade).filter(Trade.wheel_id == wheel_id)

        # Filter by outcome if provided
        if outcome is not None:
            query = query.filter(Trade.outcome == outcome)

        # Order by opened_at descending (most recent first)
        query = query.order_by(Trade.opened_at.desc())

        # Apply pagination
        trades = query.offset(skip).limit(limit).all()
        return trades

    def list_trades(
        self,
        skip: int = 0,
        limit: int = 100,
        outcome: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> list[Trade]:
        """List all trades with filtering.

        Args:
            skip: Number of records to skip (pagination)
            limit: Maximum number of records to return
            outcome: Filter by outcome if provided
            from_date: Filter trades opened on or after this date
            to_date: Filter trades opened on or before this date

        Returns:
            List of trade instances

        Example:
            >>> repo = TradeRepository(db)
            >>> trades = repo.list_trades(outcome="open", from_date=date(2026, 1, 1))
        """
        query = self.db.query(Trade)

        # Filter by outcome if provided
        if outcome is not None:
            query = query.filter(Trade.outcome == outcome)

        # Filter by date range if provided
        if from_date is not None:
            # Convert date to datetime for comparison
            from_datetime = datetime.combine(from_date, datetime.min.time())
            query = query.filter(Trade.opened_at >= from_datetime)

        if to_date is not None:
            # Convert date to datetime for comparison (end of day)
            to_datetime = datetime.combine(to_date, datetime.max.time())
            query = query.filter(Trade.opened_at <= to_datetime)

        # Order by opened_at descending (most recent first)
        query = query.order_by(Trade.opened_at.desc())

        # Apply pagination
        trades = query.offset(skip).limit(limit).all()
        return trades

    def update_trade(self, trade_id: int, trade_data: TradeUpdate) -> Optional[Trade]:
        """Update trade details.

        Only updates fields that are provided (not None) in trade_data.

        Args:
            trade_id: Trade identifier
            trade_data: Trade update data

        Returns:
            Updated trade instance if found, None otherwise

        Example:
            >>> repo = TradeRepository(db)
            >>> trade = repo.update_trade(1, TradeUpdate(premium_per_share=2.75))
        """
        # Get trade
        trade = self.get_trade(trade_id)
        if not trade:
            return None

        # Update only provided fields
        update_data = trade_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(trade, field, value)

        # Recalculate total_premium if premium_per_share or contracts changed
        if "premium_per_share" in update_data or "contracts" in update_data:
            trade.total_premium = trade.premium_per_share * trade.contracts * 100

        # Commit and refresh
        self.db.commit()
        self.db.refresh(trade)

        logger.info(f"Updated trade: {trade.id} - {trade.symbol}")
        return trade

    def delete_trade(self, trade_id: int) -> bool:
        """Delete trade.

        Args:
            trade_id: Trade identifier

        Returns:
            True if trade was deleted, False if not found

        Example:
            >>> repo = TradeRepository(db)
            >>> deleted = repo.delete_trade(1)
        """
        # Get trade
        trade = self.get_trade(trade_id)
        if not trade:
            return False

        # Delete from session
        self.db.delete(trade)
        self.db.commit()

        logger.info(f"Deleted trade: {trade_id}")
        return True

    def expire_trade(self, trade_id: int, price_at_expiry: float) -> Optional[Trade]:
        """Record trade expiration outcome.

        Determines if option expired worthless or was assigned/called away
        based on price_at_expiry vs strike.

        For puts: assigned if price <= strike
        For calls: assigned if price >= strike

        Args:
            trade_id: Trade identifier
            price_at_expiry: Stock price at expiration

        Returns:
            Updated trade instance if found, None otherwise

        Raises:
            ValueError: If trade is not in open state

        Example:
            >>> repo = TradeRepository(db)
            >>> trade = repo.expire_trade(1, 148.50)
        """
        # Get trade
        trade = self.get_trade(trade_id)
        if not trade:
            return None

        # Validate trade is open
        if trade.outcome != "open":
            raise ValueError(f"Cannot expire trade {trade_id}: already {trade.outcome}")

        # Determine outcome based on direction and price
        if trade.direction == "put":
            if price_at_expiry <= trade.strike:
                # Put assigned - buyer exercises, we buy shares at strike
                outcome = "expired_assigned"
            else:
                # Put expired worthless - keep premium, no assignment
                outcome = "expired_worthless"
        else:  # call
            if price_at_expiry >= trade.strike:
                # Call called away - buyer exercises, we sell shares at strike
                outcome = "expired_assigned"
            else:
                # Call expired worthless - keep premium and shares
                outcome = "expired_worthless"

        # Update trade
        trade.outcome = outcome
        trade.price_at_expiry = price_at_expiry
        trade.closed_at = datetime.utcnow()

        # Commit and refresh
        self.db.commit()
        self.db.refresh(trade)

        logger.info(
            f"Expired trade: {trade.id} - {trade.symbol} {outcome} "
            f"(price ${price_at_expiry:.2f} vs strike ${trade.strike:.2f})"
        )
        return trade

    def close_trade_early(self, trade_id: int, close_price: float) -> Optional[Trade]:
        """Close trade before expiration.

        Args:
            trade_id: Trade identifier
            close_price: Price paid to buy back the option (per share)

        Returns:
            Updated trade instance if found, None otherwise

        Raises:
            ValueError: If trade is not in open state

        Example:
            >>> repo = TradeRepository(db)
            >>> trade = repo.close_trade_early(1, 1.25)
        """
        # Get trade
        trade = self.get_trade(trade_id)
        if not trade:
            return None

        # Validate trade is open
        if trade.outcome != "open":
            raise ValueError(f"Cannot close trade {trade_id}: already {trade.outcome}")

        # Update trade
        trade.outcome = "closed_early"
        trade.close_price = close_price
        trade.closed_at = datetime.utcnow()

        # Commit and refresh
        self.db.commit()
        self.db.refresh(trade)

        # Calculate net premium
        net_premium = trade.total_premium - (close_price * trade.contracts * 100)
        logger.info(
            f"Closed trade early: {trade.id} - {trade.symbol} "
            f"for ${close_price:.2f}/share (net: ${net_premium:.2f})"
        )
        return trade

    def get_open_trade_for_wheel(self, wheel_id: int) -> Optional[Trade]:
        """Get the current open trade for a wheel.

        Args:
            wheel_id: Parent wheel identifier

        Returns:
            Open trade instance if found, None otherwise

        Example:
            >>> repo = TradeRepository(db)
            >>> open_trade = repo.get_open_trade_for_wheel(1)
        """
        trade = (
            self.db.query(Trade)
            .filter(and_(Trade.wheel_id == wheel_id, Trade.outcome == "open"))
            .order_by(Trade.opened_at.desc())
            .first()
        )
        return trade

    def list_open_trades(self) -> list[Trade]:
        """List all open trades across all wheels.

        Returns:
            List of open trade instances, ordered by opened_at descending

        Example:
            >>> repo = TradeRepository(db)
            >>> open_trades = repo.list_open_trades()
        """
        trades = (
            self.db.query(Trade)
            .filter(Trade.outcome == "open")
            .order_by(Trade.opened_at.desc())
            .all()
        )
        return trades
