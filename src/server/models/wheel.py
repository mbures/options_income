"""Pydantic models for Wheel API requests and responses.

This module contains request and response schemas for wheel endpoints,
including validation rules and examples.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# Valid wheel strategy profiles
VALID_PROFILES = ["conservative", "moderate", "aggressive"]


class WheelCreate(BaseModel):
    """Request schema for creating a wheel.

    Attributes:
        symbol: Stock ticker symbol (uppercase alphanumeric)
        capital_allocated: Amount of capital to allocate
        profile: Strike selection profile

    Example:
        >>> WheelCreate(
        >>>     symbol="AAPL",
        >>>     capital_allocated=10000.0,
        >>>     profile="conservative"
        >>> )
    """

    symbol: str = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Stock ticker symbol",
    )
    capital_allocated: float = Field(
        ...,
        gt=0,
        description="Amount of capital to allocate to this wheel",
    )
    profile: str = Field(
        ...,
        description="Strike selection profile (conservative, moderate, aggressive)",
    )

    @field_validator("symbol")
    @classmethod
    def symbol_must_be_uppercase_alphanumeric(cls, v: str) -> str:
        """Validate symbol is uppercase alphanumeric.

        Args:
            v: Symbol value to validate

        Returns:
            Uppercase symbol

        Raises:
            ValueError: If symbol contains invalid characters
        """
        v = v.upper().strip()
        if not v.replace(".", "").replace("-", "").isalnum():
            raise ValueError(
                "Symbol must be alphanumeric (periods and hyphens allowed)"
            )
        return v

    @field_validator("profile")
    @classmethod
    def profile_must_be_valid(cls, v: str) -> str:
        """Validate profile is one of the valid options.

        Args:
            v: Profile value to validate

        Returns:
            Lowercase profile value

        Raises:
            ValueError: If profile is not in valid profiles list
        """
        v = v.lower().strip()
        if v not in VALID_PROFILES:
            raise ValueError(f"Profile must be one of: {', '.join(VALID_PROFILES)}")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "symbol": "AAPL",
                "capital_allocated": 10000.0,
                "profile": "conservative",
            }
        }
    }


class WheelUpdate(BaseModel):
    """Request schema for updating a wheel.

    All fields are optional, but at least one must be provided.

    Attributes:
        capital_allocated: Updated capital allocation
        profile: Updated strike selection profile
        is_active: Whether wheel is active

    Example:
        >>> WheelUpdate(capital_allocated=15000.0, is_active=True)
    """

    capital_allocated: Optional[float] = Field(
        None,
        gt=0,
        description="Updated capital allocation",
    )
    profile: Optional[str] = Field(
        None,
        description="Updated strike selection profile",
    )
    is_active: Optional[bool] = Field(
        None,
        description="Whether wheel is active",
    )

    @field_validator("profile")
    @classmethod
    def profile_must_be_valid(cls, v: Optional[str]) -> Optional[str]:
        """Validate profile is one of the valid options if provided.

        Args:
            v: Profile value to validate

        Returns:
            Lowercase profile value or None

        Raises:
            ValueError: If profile is not in valid profiles list
        """
        if v is not None:
            v = v.lower().strip()
            if v not in VALID_PROFILES:
                raise ValueError(f"Profile must be one of: {', '.join(VALID_PROFILES)}")
            return v
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "capital_allocated": 15000.0,
                "profile": "moderate",
                "is_active": True,
            }
        }
    }


class WheelResponse(BaseModel):
    """Response schema for wheel data.

    Attributes:
        id: Unique wheel identifier
        portfolio_id: Parent portfolio identifier
        symbol: Stock ticker symbol
        state: Current wheel state
        shares_held: Number of shares currently held
        capital_allocated: Amount of capital allocated
        cost_basis: Average cost per share when holding shares
        profile: Strike selection profile
        created_at: Timestamp when wheel was created
        updated_at: Timestamp when wheel was last updated
        is_active: Whether wheel is currently active
        trade_count: Number of trades executed

    Example:
        >>> WheelResponse(
        >>>     id=1,
        >>>     portfolio_id="123e4567-e89b-12d3-a456-426614174000",
        >>>     symbol="AAPL",
        >>>     state="cash",
        >>>     shares_held=0,
        >>>     capital_allocated=10000.0
        >>> )
    """

    id: int = Field(..., description="Unique wheel identifier")
    portfolio_id: str = Field(..., description="Parent portfolio identifier")
    symbol: str = Field(..., description="Stock ticker symbol")
    state: str = Field(..., description="Current wheel state")
    shares_held: int = Field(..., description="Number of shares currently held")
    capital_allocated: float = Field(..., description="Amount of capital allocated")
    cost_basis: Optional[float] = Field(
        None, description="Average cost per share when holding shares"
    )
    profile: str = Field(..., description="Strike selection profile")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    is_active: bool = Field(..., description="Whether wheel is currently active")
    trade_count: int = Field(default=0, description="Number of trades executed")

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": 1,
                "portfolio_id": "123e4567-e89b-12d3-a456-426614174000",
                "symbol": "AAPL",
                "state": "cash",
                "shares_held": 0,
                "capital_allocated": 10000.0,
                "cost_basis": None,
                "profile": "conservative",
                "created_at": "2026-01-31T10:00:00",
                "updated_at": "2026-01-31T10:00:00",
                "is_active": True,
                "trade_count": 0,
            }
        },
    }


class WheelState(BaseModel):
    """Response schema for wheel current state.

    Provides a focused view of the wheel's current position state.

    Attributes:
        id: Unique wheel identifier
        symbol: Stock ticker symbol
        state: Current wheel state
        shares_held: Number of shares currently held
        cost_basis: Average cost per share when holding shares
        open_trade: Currently open trade, if any

    Example:
        >>> WheelState(
        >>>     id=1,
        >>>     symbol="AAPL",
        >>>     state="cash_put_open",
        >>>     shares_held=0,
        >>>     open_trade=None
        >>> )
    """

    id: int = Field(..., description="Unique wheel identifier")
    symbol: str = Field(..., description="Stock ticker symbol")
    state: str = Field(..., description="Current wheel state")
    shares_held: int = Field(..., description="Number of shares currently held")
    cost_basis: Optional[float] = Field(
        None, description="Average cost per share when holding shares"
    )
    open_trade: Optional[dict] = Field(None, description="Currently open trade, if any")

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": 1,
                "symbol": "AAPL",
                "state": "cash_put_open",
                "shares_held": 0,
                "cost_basis": None,
                "open_trade": {
                    "id": 1,
                    "option_type": "put",
                    "strike": 150.0,
                    "expiration": "2026-02-15",
                    "opened_at": "2026-01-31T10:00:00",
                },
            }
        },
    }
