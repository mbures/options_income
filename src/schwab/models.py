"""
Schwab-specific data models.

This module defines data models for Schwab account and position data.
These models handle the Schwab API response format and provide a clean
interface for working with Schwab account information.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class SchwabPosition:
    """
    Represents a position in a Schwab account.

    Attributes:
        symbol: Security symbol
        quantity: Number of shares/contracts held
        average_price: Average cost basis per share
        current_price: Current market price
        market_value: Total market value of position
        day_gain: Profit/loss for current day
        day_gain_percent: Day gain as percentage
        total_gain: Total profit/loss (unrealized)
        total_gain_percent: Total gain as percentage
        instrument_type: Type of instrument (EQUITY, OPTION, etc.)
        asset_type: Asset type (EQUITY, OPTION, etc.)
    """

    symbol: str
    quantity: float
    average_price: float
    current_price: float
    market_value: float
    day_gain: Optional[float] = None
    day_gain_percent: Optional[float] = None
    total_gain: Optional[float] = None
    total_gain_percent: Optional[float] = None
    instrument_type: Optional[str] = None
    asset_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation of the position
        """
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "average_price": self.average_price,
            "current_price": self.current_price,
            "market_value": self.market_value,
            "day_gain": self.day_gain,
            "day_gain_percent": self.day_gain_percent,
            "total_gain": self.total_gain,
            "total_gain_percent": self.total_gain_percent,
            "instrument_type": self.instrument_type,
            "asset_type": self.asset_type,
        }


@dataclass
class SchwabAccountBalances:
    """
    Represents account balance information.

    Attributes:
        cash_balance: Cash available for trading
        cash_available_for_trading: Cash available for immediate trading
        cash_available_for_withdrawal: Cash available for withdrawal
        market_value: Total market value of positions
        total_cash: Total cash (including sweep)
        account_value: Total account value
        buying_power: Buying power available
    """

    cash_balance: float
    cash_available_for_trading: float
    cash_available_for_withdrawal: float
    market_value: float
    total_cash: float
    account_value: float
    buying_power: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation of the balances
        """
        return {
            "cash_balance": self.cash_balance,
            "cash_available_for_trading": self.cash_available_for_trading,
            "cash_available_for_withdrawal": self.cash_available_for_withdrawal,
            "market_value": self.market_value,
            "total_cash": self.total_cash,
            "account_value": self.account_value,
            "buying_power": self.buying_power,
        }


@dataclass
class SchwabAccount:
    """
    Represents a Schwab brokerage account.

    Attributes:
        account_number: Encrypted account number (hash)
        account_type: Account type (CASH, MARGIN, etc.)
        account_nickname: User-defined nickname for account
        positions: List of positions in the account
        balances: Account balance information
        is_closing_only: Whether account is closing-only
        is_day_trader: Whether account is flagged as pattern day trader
    """

    account_number: str
    account_type: str
    positions: List[SchwabPosition]
    balances: SchwabAccountBalances
    account_nickname: Optional[str] = None
    is_closing_only: bool = False
    is_day_trader: bool = False

    def get_equity_positions(self) -> List[SchwabPosition]:
        """
        Get all equity (stock) positions.

        Returns:
            List of equity positions
        """
        return [p for p in self.positions if p.asset_type == "EQUITY"]

    def get_option_positions(self) -> List[SchwabPosition]:
        """
        Get all option positions.

        Returns:
            List of option positions
        """
        return [p for p in self.positions if p.asset_type == "OPTION"]

    def get_position(self, symbol: str) -> Optional[SchwabPosition]:
        """
        Get position by symbol.

        Args:
            symbol: Security symbol

        Returns:
            Position if found, None otherwise
        """
        for position in self.positions:
            if position.symbol == symbol:
                return position
        return None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation of the account
        """
        return {
            "account_number": self.account_number,
            "account_type": self.account_type,
            "account_nickname": self.account_nickname,
            "is_closing_only": self.is_closing_only,
            "is_day_trader": self.is_day_trader,
            "balances": self.balances.to_dict(),
            "positions": [p.to_dict() for p in self.positions],
            "total_positions": len(self.positions),
            "equity_positions": len(self.get_equity_positions()),
            "option_positions": len(self.get_option_positions()),
        }

    def __repr__(self) -> str:
        """String representation of the account."""
        return (
            f"SchwabAccount({self.account_type} ***{self.account_number[-4:]}: "
            f"{len(self.positions)} positions, ${self.balances.account_value:,.2f})"
        )
