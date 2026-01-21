"""
Main orchestrator for wheel strategy operations.

This module provides the WheelManager class which coordinates all
wheel strategy operations including position management, trade recording,
recommendations, and performance tracking.
"""

import logging
import sqlite3
from datetime import datetime
from typing import Optional

from src.finnhub_client import FinnhubClient
from src.models.profiles import StrikeProfile
from src.price_fetcher import AlphaVantagePriceDataFetcher

from .exceptions import (
    DuplicateSymbolError,
    InsufficientCapitalError,
    InvalidStateError,
    SymbolNotFoundError,
    TradeNotFoundError,
)
from .models import TradeRecord, WheelPerformance, WheelPosition, WheelRecommendation
from .performance import PerformanceTracker
from .recommend import RecommendEngine
from .repository import WheelRepository
from .state import TradeOutcome, WheelState, get_next_state

logger = logging.getLogger(__name__)


class WheelManager:
    """
    Main orchestrator for wheel strategy operations.

    Manages the lifecycle of wheel positions, enforces state machine
    rules, and coordinates between components.

    Example:
        manager = WheelManager()
        manager.create_wheel("AAPL", capital=10000, profile="conservative")
        rec = manager.get_recommendation("AAPL")
        manager.record_trade("AAPL", "put", strike=145, ...)
        manager.record_expiration("AAPL", price=148.50)
    """

    def __init__(
        self,
        db_path: str = "~/.wheel_strategy/trades.db",
        finnhub_client: Optional[FinnhubClient] = None,
        price_fetcher: Optional[AlphaVantagePriceDataFetcher] = None,
    ):
        """
        Initialize the wheel manager.

        Args:
            db_path: Path to SQLite database file
            finnhub_client: Optional FinnhubClient for live data
            price_fetcher: Optional price data fetcher
        """
        self.repository = WheelRepository(db_path)
        self.recommend_engine = RecommendEngine(finnhub_client, price_fetcher)
        self.performance_tracker = PerformanceTracker(self.repository)

    # --- Wheel CRUD Operations ---

    def create_wheel(
        self,
        symbol: str,
        capital: float,
        profile: str = "conservative",
        starting_direction: Optional[str] = None,
    ) -> WheelPosition:
        """
        Create a new wheel position starting with cash.

        Args:
            symbol: Stock ticker symbol
            capital: Cash allocated for this wheel
            profile: Risk profile (aggressive/moderate/conservative/defensive)
            starting_direction: Optional override - normally starts with puts

        Returns:
            Created WheelPosition

        Raises:
            DuplicateSymbolError: If wheel already exists for symbol
            ValueError: If profile is invalid
        """
        symbol = symbol.upper()

        # Check if wheel already exists
        existing = self.repository.get_wheel(symbol)
        if existing:
            raise DuplicateSymbolError(
                f"Wheel already exists for {symbol}. "
                f"Close it first or use a different symbol."
            )

        # Parse profile
        try:
            strike_profile = StrikeProfile(profile.lower())
        except ValueError:
            valid = [p.value for p in StrikeProfile]
            raise ValueError(f"Invalid profile '{profile}'. Valid: {valid}")

        # Create position
        position = WheelPosition(
            symbol=symbol,
            state=WheelState.CASH,
            capital_allocated=capital,
            shares_held=0,
            cost_basis=None,
            profile=strike_profile,
            is_active=True,
        )

        try:
            position = self.repository.create_wheel(position)
        except sqlite3.IntegrityError:
            raise DuplicateSymbolError(f"Wheel already exists for {symbol}")

        logger.info(
            f"Created wheel for {symbol}: ${capital:,.2f} capital, "
            f"{profile} profile"
        )
        return position

    def import_shares(
        self,
        symbol: str,
        shares: int,
        cost_basis: float,
        capital: float = 0.0,
        profile: str = "conservative",
    ) -> WheelPosition:
        """
        Import existing shares to start selling calls immediately.

        Creates wheel in SHARES state instead of CASH state.

        Args:
            symbol: Stock ticker symbol
            shares: Number of shares owned (must be multiple of 100)
            cost_basis: Average cost per share
            capital: Additional capital allocation
            profile: Risk profile

        Returns:
            Created WheelPosition in SHARES state

        Raises:
            DuplicateSymbolError: If wheel already exists
            ValueError: If shares is not a multiple of 100
        """
        symbol = symbol.upper()

        if shares % 100 != 0:
            raise ValueError(
                f"Shares must be a multiple of 100 for covered calls. "
                f"Got {shares}."
            )

        if shares <= 0:
            raise ValueError("Shares must be positive")

        # Check if wheel already exists
        existing = self.repository.get_wheel(symbol)
        if existing:
            raise DuplicateSymbolError(f"Wheel already exists for {symbol}")

        # Parse profile
        try:
            strike_profile = StrikeProfile(profile.lower())
        except ValueError:
            valid = [p.value for p in StrikeProfile]
            raise ValueError(f"Invalid profile '{profile}'. Valid: {valid}")

        # Create position in SHARES state
        position = WheelPosition(
            symbol=symbol,
            state=WheelState.SHARES,
            capital_allocated=capital,
            shares_held=shares,
            cost_basis=cost_basis,
            profile=strike_profile,
            is_active=True,
        )

        try:
            position = self.repository.create_wheel(position)
        except sqlite3.IntegrityError:
            raise DuplicateSymbolError(f"Wheel already exists for {symbol}")

        logger.info(
            f"Imported {shares} shares of {symbol} @ ${cost_basis:.2f}, "
            f"ready for covered calls"
        )
        return position

    def get_wheel(self, symbol: str) -> Optional[WheelPosition]:
        """Get a wheel position by symbol."""
        return self.repository.get_wheel(symbol.upper())

    def list_wheels(self, active_only: bool = True) -> list[WheelPosition]:
        """List all wheel positions."""
        return self.repository.list_wheels(active_only)

    def close_wheel(self, symbol: str) -> None:
        """
        Close/deactivate a wheel position.

        Args:
            symbol: Stock ticker symbol

        Raises:
            SymbolNotFoundError: If wheel doesn't exist
            InvalidStateError: If wheel has open positions
        """
        symbol = symbol.upper()
        wheel = self.repository.get_wheel(symbol)

        if not wheel:
            raise SymbolNotFoundError(f"No wheel found for {symbol}")

        if wheel.has_open_position:
            raise InvalidStateError(
                f"Cannot close wheel with open position. "
                f"Current state: {wheel.state.value}. "
                f"Record expiration or close trade first."
            )

        self.repository.delete_wheel(symbol)
        logger.info(f"Closed wheel for {symbol}")

    def update_profile(self, symbol: str, profile: str) -> WheelPosition:
        """
        Update the risk profile for a wheel.

        Args:
            symbol: Stock ticker symbol
            profile: New risk profile

        Returns:
            Updated WheelPosition
        """
        symbol = symbol.upper()
        wheel = self.repository.get_wheel(symbol)

        if not wheel:
            raise SymbolNotFoundError(f"No wheel found for {symbol}")

        try:
            strike_profile = StrikeProfile(profile.lower())
        except ValueError:
            valid = [p.value for p in StrikeProfile]
            raise ValueError(f"Invalid profile '{profile}'. Valid: {valid}")

        wheel.profile = strike_profile
        self.repository.update_wheel(wheel)

        logger.info(f"Updated {symbol} profile to {profile}")
        return wheel

    # --- Recommendations ---

    def get_recommendation(self, symbol: str) -> WheelRecommendation:
        """
        Get recommendation based on current state.

        CASH state -> recommend put to sell
        SHARES state -> recommend call to sell
        OPEN states -> error (must wait for expiration)

        Args:
            symbol: Stock ticker symbol

        Returns:
            WheelRecommendation for next trade

        Raises:
            SymbolNotFoundError: If wheel doesn't exist
            InvalidStateError: If wheel has open position
        """
        symbol = symbol.upper()
        wheel = self.repository.get_wheel(symbol)

        if not wheel:
            raise SymbolNotFoundError(f"No wheel found for {symbol}")

        return self.recommend_engine.get_recommendation(wheel)

    def get_all_recommendations(self) -> list[WheelRecommendation]:
        """
        Get recommendations for all active wheels without open positions.

        Returns:
            List of WheelRecommendation for each eligible wheel
        """
        recommendations = []
        wheels = self.repository.list_wheels(active_only=True)

        for wheel in wheels:
            if not wheel.has_open_position:
                try:
                    rec = self.recommend_engine.get_recommendation(wheel)
                    recommendations.append(rec)
                except Exception as e:
                    logger.warning(
                        f"Could not get recommendation for {wheel.symbol}: {e}"
                    )

        return recommendations

    # --- Trade Recording ---

    def record_trade(
        self,
        symbol: str,
        direction: str,
        strike: float,
        expiration_date: str,
        premium: float,
        contracts: int = 1,
    ) -> TradeRecord:
        """
        Record a sold option. Validates state allows this direction.

        Selling put: must be in CASH state -> transitions to CASH_PUT_OPEN
        Selling call: must be in SHARES state -> transitions to SHARES_CALL_OPEN

        Args:
            symbol: Stock ticker symbol
            direction: "put" or "call"
            strike: Strike price
            expiration_date: Expiration date (YYYY-MM-DD)
            premium: Premium received per share
            contracts: Number of contracts sold

        Returns:
            Created TradeRecord

        Raises:
            SymbolNotFoundError: If wheel doesn't exist
            InvalidStateError: If state doesn't allow this trade
            InsufficientCapitalError: If not enough capital/shares
        """
        symbol = symbol.upper()
        direction = direction.lower()

        if direction not in ("put", "call"):
            raise ValueError(f"Direction must be 'put' or 'call', got '{direction}'")

        wheel = self.repository.get_wheel(symbol)
        if not wheel:
            raise SymbolNotFoundError(f"No wheel found for {symbol}")

        # Validate state transition
        if direction == "put":
            if wheel.state != WheelState.CASH:
                raise InvalidStateError(
                    f"Cannot sell put in state {wheel.state.value}. "
                    f"Must be in CASH state."
                )
            # Check capital
            required_capital = strike * contracts * 100
            if required_capital > wheel.capital_allocated:
                raise InsufficientCapitalError(
                    f"Need ${required_capital:,.2f} for {contracts} contracts @ "
                    f"${strike} strike, but only ${wheel.capital_allocated:,.2f} allocated"
                )
            action = "sell_put"
        else:  # call
            if wheel.state != WheelState.SHARES:
                raise InvalidStateError(
                    f"Cannot sell call in state {wheel.state.value}. "
                    f"Must be in SHARES state."
                )
            # Check shares
            required_shares = contracts * 100
            if required_shares > wheel.shares_held:
                raise InsufficientCapitalError(
                    f"Need {required_shares} shares for {contracts} contracts, "
                    f"but only {wheel.shares_held} held"
                )
            action = "sell_call"

        # Create trade record
        trade = TradeRecord(
            wheel_id=wheel.id,
            symbol=symbol,
            direction=direction,
            strike=strike,
            expiration_date=expiration_date,
            premium_per_share=premium,
            contracts=contracts,
            total_premium=premium * contracts * 100,
            outcome=TradeOutcome.OPEN,
        )
        trade = self.repository.create_trade(trade)

        # Transition state
        new_state = get_next_state(wheel.state, action)
        wheel.state = new_state
        self.repository.update_wheel(wheel)

        logger.info(
            f"Recorded trade: SELL {contracts}x {symbol} ${strike} {direction.upper()} "
            f"for ${trade.total_premium:.2f} premium"
        )
        return trade

    def record_expiration(
        self,
        symbol: str,
        price_at_expiry: float,
    ) -> TradeOutcome:
        """
        Record expiration outcome and transition state.

        Determines if option expired worthless or was assigned/exercised
        based on price_at_expiry vs strike.

        PUT expired OTM (price > strike): CASH_PUT_OPEN -> CASH
        PUT assigned (price <= strike): CASH_PUT_OPEN -> SHARES
        CALL expired OTM (price < strike): SHARES_CALL_OPEN -> SHARES
        CALL called away (price >= strike): SHARES_CALL_OPEN -> CASH

        Args:
            symbol: Stock ticker symbol
            price_at_expiry: Stock price at market close on expiration day

        Returns:
            TradeOutcome indicating what happened

        Raises:
            SymbolNotFoundError: If wheel doesn't exist
            TradeNotFoundError: If no open trade found
            InvalidStateError: If not in an OPEN state
        """
        symbol = symbol.upper()
        wheel = self.repository.get_wheel(symbol)

        if not wheel:
            raise SymbolNotFoundError(f"No wheel found for {symbol}")

        if not wheel.has_open_position:
            raise InvalidStateError(
                f"No open position to expire. Current state: {wheel.state.value}"
            )

        # Get open trade
        trade = self.repository.get_open_trade(wheel.id)
        if not trade:
            raise TradeNotFoundError(f"No open trade found for {symbol}")

        # Determine outcome
        if trade.direction == "put":
            if price_at_expiry > trade.strike:
                # Put expired OTM - keep premium, stay in cash
                outcome = TradeOutcome.EXPIRED_WORTHLESS
                action = "expired_otm"
            else:
                # Put assigned - bought shares at strike
                outcome = TradeOutcome.ASSIGNED
                action = "assigned"
                # Update shares
                shares_acquired = trade.contracts * 100
                wheel.shares_held = shares_acquired
                wheel.cost_basis = trade.strike
        else:  # call
            if price_at_expiry < trade.strike:
                # Call expired OTM - keep premium, keep shares
                outcome = TradeOutcome.EXPIRED_WORTHLESS
                action = "expired_otm"
            else:
                # Call exercised - sold shares at strike
                outcome = TradeOutcome.CALLED_AWAY
                action = "called_away"
                # Update shares
                wheel.shares_held = 0
                wheel.cost_basis = None

        # Update trade
        trade.outcome = outcome
        trade.price_at_expiry = price_at_expiry
        trade.closed_at = datetime.now()
        self.repository.update_trade(trade)

        # Transition state
        new_state = get_next_state(wheel.state, action)
        wheel.state = new_state
        self.repository.update_wheel(wheel)

        logger.info(
            f"Recorded expiration for {symbol}: {outcome.value} "
            f"(price ${price_at_expiry:.2f} vs strike ${trade.strike:.2f})"
        )
        return outcome

    def close_trade_early(
        self,
        symbol: str,
        close_price: float,
    ) -> TradeRecord:
        """
        Buy back option early (before expiration).

        Args:
            symbol: Stock ticker symbol
            close_price: Price paid to buy back the option (per share)

        Returns:
            Updated TradeRecord

        Raises:
            SymbolNotFoundError: If wheel doesn't exist
            TradeNotFoundError: If no open trade found
        """
        symbol = symbol.upper()
        wheel = self.repository.get_wheel(symbol)

        if not wheel:
            raise SymbolNotFoundError(f"No wheel found for {symbol}")

        trade = self.repository.get_open_trade(wheel.id)
        if not trade:
            raise TradeNotFoundError(f"No open trade found for {symbol}")

        # Update trade
        trade.outcome = TradeOutcome.CLOSED_EARLY
        trade.close_price = close_price
        trade.closed_at = datetime.now()
        self.repository.update_trade(trade)

        # Transition state
        action = "closed_early"
        new_state = get_next_state(wheel.state, action)
        wheel.state = new_state
        self.repository.update_wheel(wheel)

        net_premium = trade.net_premium
        logger.info(
            f"Closed {symbol} trade early for ${close_price:.2f}/share. "
            f"Net premium: ${net_premium:.2f}"
        )
        return trade

    # --- Performance ---

    def get_performance(self, symbol: str) -> WheelPerformance:
        """Get performance metrics for a symbol."""
        return self.performance_tracker.get_performance(symbol.upper())

    def get_portfolio_performance(self) -> WheelPerformance:
        """Get aggregate performance across all wheels."""
        return self.performance_tracker.get_portfolio_performance()

    def export_trades(
        self,
        symbol: Optional[str] = None,
        format: str = "csv",
    ) -> str:
        """
        Export trade history.

        Args:
            symbol: Optional symbol filter
            format: "csv" or "json"

        Returns:
            Formatted trade data
        """
        return self.performance_tracker.export_trades(symbol, format)

    # --- Utility ---

    def get_open_trade(self, symbol: str) -> Optional[TradeRecord]:
        """Get the currently open trade for a symbol."""
        wheel = self.repository.get_wheel(symbol.upper())
        if not wheel:
            return None
        return self.repository.get_open_trade(wheel.id)

    def get_trade_history(self, symbol: str) -> list[TradeRecord]:
        """Get all trades for a symbol."""
        wheel = self.repository.get_wheel(symbol.upper())
        if not wheel:
            return []
        return self.repository.get_trades(wheel_id=wheel.id)
