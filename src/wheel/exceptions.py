"""Custom exceptions for wheel strategy operations."""


class WheelError(Exception):
    """Base exception for wheel operations."""

    pass


class InvalidStateError(WheelError):
    """Operation not allowed in current state."""

    pass


class SymbolNotFoundError(WheelError):
    """Wheel position not found for symbol."""

    pass


class TradeNotFoundError(WheelError):
    """No open trade found."""

    pass


class DuplicateSymbolError(WheelError):
    """Wheel already exists for this symbol."""

    pass


class InsufficientCapitalError(WheelError):
    """Not enough capital for the operation."""

    pass


class DataFetchError(WheelError):
    """Error fetching market data."""

    pass
