"""Pydantic models for Wheel API requests and responses.

This module contains request and response schemas for wheel endpoints,
including validation rules and examples.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# Valid wheel strategy profiles
VALID_PROFILES = ["conservative", "moderate", "aggressive", "defensive"]

# Valid initial wheel states
VALID_INITIAL_STATES = ["cash", "shares"]


class WheelCreate(BaseModel):
    """Request schema for creating a wheel.

    Supports two start modes:
    - Cash mode: provide capital_allocated to start selling puts
    - Shares mode: provide shares_held and cost_basis to start selling calls

    Attributes:
        symbol: Stock ticker symbol (uppercase alphanumeric)
        capital_allocated: Amount of capital to allocate (required for cash start)
        profile: Strike selection profile
        shares_held: Number of shares held (required for shares start)
        cost_basis: Average cost per share (required for shares start)
        state: Initial wheel state ("cash" or "shares")
    """

    symbol: str = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Stock ticker symbol",
    )
    capital_allocated: Optional[float] = Field(
        None,
        gt=0,
        description="Amount of capital to allocate to this wheel",
    )
    profile: str = Field(
        ...,
        description="Strike selection profile",
    )
    shares: Optional[int] = Field(
        None,
        gt=0,
        description="Number of shares held (for shares start mode)",
    )
    cost_basis: Optional[float] = Field(
        None,
        gt=0,
        description="Average cost per share (for shares start mode)",
    )
    state: Optional[str] = Field(
        None,
        description="Initial wheel state (cash or shares)",
    )

    @field_validator("symbol")
    @classmethod
    def symbol_must_be_uppercase_alphanumeric(cls, v: str) -> str:
        """Validate symbol is uppercase alphanumeric."""
        v = v.upper().strip()
        if not v.replace(".", "").replace("-", "").isalnum():
            raise ValueError(
                "Symbol must be alphanumeric (periods and hyphens allowed)"
            )
        return v

    @field_validator("profile")
    @classmethod
    def profile_must_be_valid(cls, v: str) -> str:
        """Validate profile is one of the valid options."""
        v = v.lower().strip()
        if v not in VALID_PROFILES:
            raise ValueError(f"Profile must be one of: {', '.join(VALID_PROFILES)}")
        return v

    @field_validator("state")
    @classmethod
    def state_must_be_valid(cls, v: Optional[str]) -> Optional[str]:
        """Validate initial state is one of the valid options."""
        if v is not None:
            v = v.lower().strip()
            if v not in VALID_INITIAL_STATES:
                raise ValueError(
                    f"State must be one of: {', '.join(VALID_INITIAL_STATES)}"
                )
        return v

    @model_validator(mode="after")
    def validate_start_mode(self) -> "WheelCreate":
        """Ensure either capital_allocated OR (shares + cost_basis) is provided.

        When starting with shares, capital_allocated is computed as shares * cost_basis.
        When starting with cash, state defaults to 'cash'.
        """
        has_capital = self.capital_allocated is not None
        has_shares = self.shares is not None and self.cost_basis is not None

        if not has_capital and not has_shares:
            raise ValueError(
                "Must provide either capital_allocated or both shares and cost_basis"
            )

        # If starting with shares, compute capital_allocated and default state
        if has_shares and not has_capital:
            self.capital_allocated = self.shares * self.cost_basis
            if self.state is None:
                self.state = "shares"

        # Default state to cash if not set
        if self.state is None:
            self.state = "cash"

        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "symbol": "AAPL",
                    "capital_allocated": 10000.0,
                    "profile": "conservative",
                },
                {
                    "symbol": "NVDA",
                    "shares": 3600,
                    "cost_basis": 120.0,
                    "state": "shares",
                    "profile": "moderate",
                },
            ]
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
