"""Service layer for wheel operations with state machine validation.

This module provides business logic for wheel trade operations,
integrating state machine validation from WheelManager with the
new API database layer.
"""

import logging

from sqlalchemy.orm import Session

from src.server.database.models.wheel import Wheel
from src.server.models.trade import TradeCloseRequest, TradeCreate, TradeExpireRequest
from src.server.repositories.trade import TradeRepository
from src.server.repositories.wheel import WheelRepository
from src.wheel.state import WheelState, get_next_state

logger = logging.getLogger(__name__)


class WheelService:
    """Service layer for wheel operations with state machine validation.

    This service enforces wheel strategy state machine rules while
    using the new database layer. It validates state transitions
    before recording trades and updates wheel state accordingly.

    Attributes:
        db: SQLAlchemy database session
        wheel_repo: Repository for wheel operations
        trade_repo: Repository for trade operations
    """

    def __init__(self, db: Session):
        """Initialize wheel service.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db
        self.wheel_repo = WheelRepository(db)
        self.trade_repo = TradeRepository(db)

    def _get_wheel_state_enum(self, state_str: str) -> WheelState:
        """Convert string state to WheelState enum.

        Args:
            state_str: State string from database

        Returns:
            WheelState enum value

        Raises:
            ValueError: If state string is invalid
        """
        state_map = {
            "cash": WheelState.CASH,
            "cash_put_open": WheelState.CASH_PUT_OPEN,
            "shares": WheelState.SHARES,
            "shares_call_open": WheelState.SHARES_CALL_OPEN,
        }
        if state_str not in state_map:
            raise ValueError(f"Invalid state: {state_str}")
        return state_map[state_str]

    def _update_wheel_state(self, wheel: Wheel, new_state: WheelState) -> None:
        """Update wheel state in database.

        Args:
            wheel: Wheel instance to update
            new_state: New state to set
        """
        wheel.state = new_state.value
        self.db.commit()
        self.db.refresh(wheel)
        logger.info(f"Updated wheel {wheel.id} state to {new_state.value}")

    def record_trade(self, wheel_id: int, trade_data: TradeCreate):
        """Record a new trade with state machine validation.

        Validates that the wheel state allows this trade direction,
        then creates the trade and transitions the wheel state.

        Args:
            wheel_id: Parent wheel identifier
            trade_data: Trade creation data

        Returns:
            Created trade instance

        Raises:
            ValueError: If wheel not found or invalid state transition

        Example:
            >>> service = WheelService(db)
            >>> trade = service.record_trade(
            >>>     1,
            >>>     TradeCreate(direction="put", strike=150.0, ...)
            >>> )
        """
        # Get wheel
        wheel = self.wheel_repo.get_wheel(wheel_id)
        if not wheel:
            raise ValueError(f"Wheel not found: {wheel_id}")

        # Get current state as enum
        current_state = self._get_wheel_state_enum(wheel.state)

        # Validate state allows this trade direction
        direction = trade_data.direction.lower()
        if direction == "put":
            if current_state != WheelState.CASH:
                raise ValueError(
                    f"Cannot sell put in state {wheel.state}. "
                    f"Must be in CASH state."
                )
            action = "sell_put"

            # Validate sufficient capital
            required_capital = trade_data.strike * trade_data.contracts * 100
            if required_capital > wheel.capital_allocated:
                raise ValueError(
                    f"Insufficient capital: need ${required_capital:,.2f} "
                    f"but only ${wheel.capital_allocated:,.2f} allocated"
                )
        else:  # call
            if current_state != WheelState.SHARES:
                raise ValueError(
                    f"Cannot sell call in state {wheel.state}. "
                    f"Must be in SHARES state."
                )
            action = "sell_call"

            # Validate sufficient shares
            required_shares = trade_data.contracts * 100
            if required_shares > wheel.shares_held:
                raise ValueError(
                    f"Insufficient shares: need {required_shares} "
                    f"but only {wheel.shares_held} held"
                )

        # Get next state after this action
        try:
            new_state = get_next_state(current_state, action)
        except ValueError as e:
            logger.error(f"Invalid state transition: {e}")
            raise ValueError(f"Invalid state transition: {str(e)}") from e

        # Create trade in database
        trade = self.trade_repo.create_trade(wheel_id, trade_data)

        # Update wheel state
        self._update_wheel_state(wheel, new_state)

        logger.info(
            f"Recorded trade: {trade.id} - {wheel.symbol} {direction} "
            f"${trade.strike} x {trade.contracts} contracts, "
            f"state: {current_state.value} -> {new_state.value}"
        )
        return trade

    def expire_trade(self, trade_id: int, expire_request: TradeExpireRequest):
        """Record trade expiration with state machine validation.

        Determines outcome based on price vs strike, updates the trade,
        and transitions wheel state accordingly. Handles share assignment
        for puts and share removal for calls.

        Args:
            trade_id: Trade identifier
            expire_request: Expiration request with price_at_expiry

        Returns:
            Updated trade instance

        Raises:
            ValueError: If trade not found, not open, or invalid state

        Example:
            >>> service = WheelService(db)
            >>> trade = service.expire_trade(
            >>>     1,
            >>>     TradeExpireRequest(price_at_expiry=148.50)
            >>> )
        """
        # Get trade
        trade = self.trade_repo.get_trade(trade_id)
        if not trade:
            raise ValueError(f"Trade not found: {trade_id}")

        # Validate trade is open
        if trade.outcome != "open":
            raise ValueError(f"Trade {trade_id} is not open (current: {trade.outcome})")

        # Get wheel
        wheel = self.wheel_repo.get_wheel(trade.wheel_id)
        if not wheel:
            raise ValueError(f"Wheel not found: {trade.wheel_id}")

        # Get current state as enum
        current_state = self._get_wheel_state_enum(wheel.state)

        # Determine action based on direction and price
        price_at_expiry = expire_request.price_at_expiry

        if trade.direction == "put":
            if price_at_expiry <= trade.strike:
                # Put assigned - we buy shares at strike
                action = "assigned"
                # Update wheel shares
                shares_acquired = trade.contracts * 100
                wheel.shares_held = shares_acquired
                wheel.cost_basis = trade.strike
                logger.info(
                    f"Put assigned: acquired {shares_acquired} shares "
                    f"of {wheel.symbol} @ ${trade.strike:.2f}"
                )
            else:
                # Put expired worthless - keep premium
                action = "expired_otm"
        else:  # call
            if price_at_expiry >= trade.strike:
                # Call called away - we sell shares at strike
                action = "called_away"
                # Update wheel shares
                wheel.shares_held = 0
                wheel.cost_basis = None
                logger.info(
                    f"Call called away: sold shares of {wheel.symbol} "
                    f"@ ${trade.strike:.2f}"
                )
            else:
                # Call expired worthless - keep premium and shares
                action = "expired_otm"

        # Get next state after this action
        try:
            new_state = get_next_state(current_state, action)
        except ValueError as e:
            logger.error(f"Invalid state transition during expiration: {e}")
            raise ValueError(f"Invalid expiration: {str(e)}") from e

        # Update trade in database (this sets outcome and price_at_expiry)
        updated_trade = self.trade_repo.expire_trade(trade_id, price_at_expiry)
        if not updated_trade:
            raise ValueError(f"Failed to update trade {trade_id}")

        # Update wheel state and shares
        self._update_wheel_state(wheel, new_state)

        logger.info(
            f"Expired trade: {trade.id} - {wheel.symbol} {updated_trade.outcome} "
            f"(price ${price_at_expiry:.2f} vs strike ${trade.strike:.2f}), "
            f"state: {current_state.value} -> {new_state.value}"
        )
        return updated_trade

    def close_trade_early(self, trade_id: int, close_request: TradeCloseRequest):
        """Close trade early with state machine validation.

        Buys back the option before expiration and transitions wheel
        state back to the base state (CASH or SHARES).

        Args:
            trade_id: Trade identifier
            close_request: Close request with close_price

        Returns:
            Updated trade instance

        Raises:
            ValueError: If trade not found, not open, or invalid state

        Example:
            >>> service = WheelService(db)
            >>> trade = service.close_trade_early(
            >>>     1,
            >>>     TradeCloseRequest(close_price=1.25)
            >>> )
        """
        # Get trade
        trade = self.trade_repo.get_trade(trade_id)
        if not trade:
            raise ValueError(f"Trade not found: {trade_id}")

        # Validate trade is open
        if trade.outcome != "open":
            raise ValueError(f"Trade {trade_id} is not open (current: {trade.outcome})")

        # Get wheel
        wheel = self.wheel_repo.get_wheel(trade.wheel_id)
        if not wheel:
            raise ValueError(f"Wheel not found: {trade.wheel_id}")

        # Get current state as enum
        current_state = self._get_wheel_state_enum(wheel.state)

        # Action is always closed_early
        action = "closed_early"

        # Get next state after this action
        try:
            new_state = get_next_state(current_state, action)
        except ValueError as e:
            logger.error(f"Invalid state transition during early close: {e}")
            raise ValueError(f"Invalid close: {str(e)}") from e

        # Update trade in database (this sets outcome and close_price)
        updated_trade = self.trade_repo.close_trade_early(trade_id, close_request.close_price)
        if not updated_trade:
            raise ValueError(f"Failed to update trade {trade_id}")

        # Update wheel state
        self._update_wheel_state(wheel, new_state)

        # Calculate net premium
        net_premium = updated_trade.total_premium - (close_request.close_price * trade.contracts * 100)
        logger.info(
            f"Closed trade early: {trade.id} - {wheel.symbol} "
            f"for ${close_request.close_price:.2f}/share (net: ${net_premium:.2f}), "
            f"state: {current_state.value} -> {new_state.value}"
        )
        return updated_trade
