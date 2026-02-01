"""Pydantic models for Trade API requests and responses.

This module contains request and response schemas for trade endpoints,
including validation rules and examples for option trade operations.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class TradeCreate(BaseModel):
    """Request schema for recording a new trade.

    Attributes:
        direction: Trade direction ('put' or 'call')
        strike: Strike price
        expiration_date: Expiration date (YYYY-MM-DD)
        premium_per_share: Premium collected per share
        contracts: Number of contracts (100 shares each)

    Example:
        >>> TradeCreate(
        >>>     direction="put",
        >>>     strike=150.0,
        >>>     expiration_date="2026-03-20",
        >>>     premium_per_share=2.50,
        >>>     contracts=1
        >>> )
    """

    direction: str = Field(..., description="Trade direction: 'put' or 'call'")
    strike: float = Field(..., gt=0, description="Strike price")
    expiration_date: str = Field(..., description="Expiration date (YYYY-MM-DD)")
    premium_per_share: float = Field(..., gt=0, description="Premium per share")
    contracts: int = Field(..., gt=0, description="Number of contracts")

    @field_validator("direction")
    @classmethod
    def validate_direction(cls, v: str) -> str:
        """Validate direction is 'put' or 'call'.

        Args:
            v: Direction value to validate

        Returns:
            Lowercase direction value

        Raises:
            ValueError: If direction is not 'put' or 'call'
        """
        v = v.lower().strip()
        if v not in ["put", "call"]:
            raise ValueError('Direction must be "put" or "call"')
        return v

    @field_validator("expiration_date")
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        """Validate expiration date format and ensure it's a future date.

        Args:
            v: Date string to validate

        Returns:
            Validated date string in YYYY-MM-DD format

        Raises:
            ValueError: If date format is invalid or date is in the past
        """
        from datetime import date

        v = v.strip()

        # Parse date to validate format
        try:
            expiry = date.fromisoformat(v)
        except ValueError as e:
            raise ValueError("Expiration date must be in YYYY-MM-DD format") from e

        # Validate it's a future date
        today = date.today()
        if expiry <= today:
            raise ValueError("Expiration date must be in the future")

        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "direction": "put",
                "strike": 150.0,
                "expiration_date": "2026-03-20",
                "premium_per_share": 2.50,
                "contracts": 1,
            }
        }
    }


class TradeUpdate(BaseModel):
    """Request schema for updating trade details.

    All fields are optional. Only provided fields will be updated.

    Attributes:
        premium_per_share: Updated premium per share
        contracts: Updated number of contracts
        strike: Updated strike price
        expiration_date: Updated expiration date

    Example:
        >>> TradeUpdate(premium_per_share=2.75)
    """

    premium_per_share: Optional[float] = Field(None, gt=0, description="Updated premium per share")
    contracts: Optional[int] = Field(None, gt=0, description="Updated number of contracts")
    strike: Optional[float] = Field(None, gt=0, description="Updated strike price")
    expiration_date: Optional[str] = Field(None, description="Updated expiration date (YYYY-MM-DD)")

    @field_validator("expiration_date")
    @classmethod
    def validate_date_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate expiration date format if provided.

        Args:
            v: Date string to validate

        Returns:
            Validated date string or None

        Raises:
            ValueError: If date format is invalid
        """
        if v is None:
            return v

        from datetime import date

        v = v.strip()

        # Parse date to validate format
        try:
            date.fromisoformat(v)
        except ValueError as e:
            raise ValueError("Expiration date must be in YYYY-MM-DD format") from e

        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "premium_per_share": 2.75,
                "contracts": 2,
            }
        }
    }


class TradeResponse(BaseModel):
    """Response schema for trade data.

    Attributes:
        id: Unique trade identifier
        wheel_id: Parent wheel identifier
        symbol: Stock ticker symbol
        direction: Trade direction ('put' or 'call')
        strike: Strike price
        expiration_date: Expiration date (YYYY-MM-DD)
        premium_per_share: Premium collected per share
        contracts: Number of contracts
        total_premium: Total premium collected
        opened_at: Timestamp when trade was opened
        closed_at: Timestamp when trade was closed (if applicable)
        outcome: Trade outcome
        price_at_expiry: Stock price at expiration (if applicable)
        close_price: Premium paid to close early (if applicable)

    Example:
        >>> TradeResponse(
        >>>     id=1,
        >>>     wheel_id=1,
        >>>     symbol="AAPL",
        >>>     direction="put",
        >>>     strike=150.0,
        >>>     total_premium=250.0
        >>> )
    """

    id: int = Field(..., description="Unique trade identifier")
    wheel_id: int = Field(..., description="Parent wheel identifier")
    symbol: str = Field(..., description="Stock ticker symbol")
    direction: str = Field(..., description="Trade direction ('put' or 'call')")
    strike: float = Field(..., description="Strike price")
    expiration_date: str = Field(..., description="Expiration date (YYYY-MM-DD)")
    premium_per_share: float = Field(..., description="Premium collected per share")
    contracts: int = Field(..., description="Number of contracts")
    total_premium: float = Field(..., description="Total premium collected")
    opened_at: datetime = Field(..., description="Timestamp when trade was opened")
    closed_at: Optional[datetime] = Field(None, description="Timestamp when trade was closed")
    outcome: str = Field(..., description="Trade outcome")
    price_at_expiry: Optional[float] = Field(None, description="Stock price at expiration")
    close_price: Optional[float] = Field(None, description="Premium paid to close early")

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": 1,
                "wheel_id": 1,
                "symbol": "AAPL",
                "direction": "put",
                "strike": 150.0,
                "expiration_date": "2026-03-20",
                "premium_per_share": 2.50,
                "contracts": 1,
                "total_premium": 250.0,
                "opened_at": "2026-02-01T10:00:00",
                "closed_at": None,
                "outcome": "open",
                "price_at_expiry": None,
                "close_price": None,
            }
        },
    }


class TradeExpireRequest(BaseModel):
    """Request schema for recording trade expiration.

    Attributes:
        price_at_expiry: Stock price at expiration

    Example:
        >>> TradeExpireRequest(price_at_expiry=148.50)
    """

    price_at_expiry: float = Field(..., gt=0, description="Stock price at expiration")

    model_config = {
        "json_schema_extra": {
            "example": {
                "price_at_expiry": 148.50,
            }
        }
    }


class TradeCloseRequest(BaseModel):
    """Request schema for closing trade early.

    Attributes:
        close_price: Price paid to close position (per share)

    Example:
        >>> TradeCloseRequest(close_price=1.25)
    """

    close_price: float = Field(..., gt=0, description="Price paid to close position (per share)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "close_price": 1.25,
            }
        }
    }
