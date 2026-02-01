"""Pydantic models for Portfolio API requests and responses.

This module contains request and response schemas for portfolio endpoints,
including validation rules and examples.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class PortfolioCreate(BaseModel):
    """Request schema for creating a portfolio.

    Attributes:
        name: Portfolio name (required, non-empty)
        description: Optional detailed description
        default_capital: Default capital allocation for new wheels

    Example:
        >>> PortfolioCreate(
        >>>     name="Primary Trading",
        >>>     description="Main wheel strategy portfolio",
        >>>     default_capital=50000.0
        >>> )
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Portfolio name",
    )
    description: Optional[str] = Field(
        None,
        max_length=500,
        description="Portfolio description",
    )
    default_capital: Optional[float] = Field(
        None,
        ge=0,
        description="Default capital allocation for new wheels",
    )

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        """Validate that name is not blank or whitespace only.

        Args:
            v: Name value to validate

        Returns:
            Stripped name value

        Raises:
            ValueError: If name is blank or whitespace only
        """
        if not v or not v.strip():
            raise ValueError("Name cannot be blank")
        return v.strip()

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Primary Trading",
                "description": "Main wheel strategy portfolio",
                "default_capital": 50000.0,
            }
        }
    }


class PortfolioUpdate(BaseModel):
    """Request schema for updating a portfolio.

    All fields are optional, but at least one must be provided.

    Attributes:
        name: Updated portfolio name
        description: Updated description
        default_capital: Updated default capital allocation

    Example:
        >>> PortfolioUpdate(name="Updated Portfolio Name")
    """

    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=100,
        description="Updated portfolio name",
    )
    description: Optional[str] = Field(
        None,
        max_length=500,
        description="Updated portfolio description",
    )
    default_capital: Optional[float] = Field(
        None,
        ge=0,
        description="Updated default capital allocation",
    )

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: Optional[str]) -> Optional[str]:
        """Validate that name is not blank if provided.

        Args:
            v: Name value to validate

        Returns:
            Stripped name value or None

        Raises:
            ValueError: If name is blank or whitespace only
        """
        if v is not None:
            if not v or not v.strip():
                raise ValueError("Name cannot be blank")
            return v.strip()
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Updated Portfolio",
                "default_capital": 75000.0,
            }
        }
    }


class PortfolioResponse(BaseModel):
    """Response schema for portfolio data.

    Attributes:
        id: Unique portfolio identifier (UUID)
        name: Portfolio name
        description: Portfolio description
        default_capital: Default capital allocation
        created_at: Timestamp when portfolio was created
        updated_at: Timestamp when portfolio was last updated
        wheel_count: Number of wheels in portfolio

    Example:
        >>> PortfolioResponse(
        >>>     id="123e4567-e89b-12d3-a456-426614174000",
        >>>     name="Primary Trading",
        >>>     description="Main portfolio",
        >>>     default_capital=50000.0,
        >>>     created_at=datetime.utcnow(),
        >>>     updated_at=datetime.utcnow(),
        >>>     wheel_count=5
        >>> )
    """

    id: str = Field(..., description="Unique portfolio identifier")
    name: str = Field(..., description="Portfolio name")
    description: Optional[str] = Field(None, description="Portfolio description")
    default_capital: Optional[float] = Field(
        None, description="Default capital allocation"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    wheel_count: int = Field(default=0, description="Number of wheels in portfolio")

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "name": "Primary Trading",
                "description": "Main wheel strategy portfolio",
                "default_capital": 50000.0,
                "created_at": "2026-01-31T10:00:00",
                "updated_at": "2026-01-31T10:00:00",
                "wheel_count": 5,
            }
        },
    }


class PortfolioSummary(PortfolioResponse):
    """Extended response schema with portfolio statistics.

    Extends PortfolioResponse with additional computed statistics.

    Attributes:
        total_wheels: Total number of wheels
        active_wheels: Number of active wheels
        total_capital_allocated: Sum of capital allocated across all wheels
        total_positions_value: Total value of current positions

    Example:
        >>> PortfolioSummary(
        >>>     id="123e4567-e89b-12d3-a456-426614174000",
        >>>     name="Primary Trading",
        >>>     total_wheels=10,
        >>>     active_wheels=8,
        >>>     total_capital_allocated=100000.0
        >>> )
    """

    total_wheels: int = Field(default=0, description="Total number of wheels")
    active_wheels: int = Field(default=0, description="Number of active wheels")
    total_capital_allocated: float = Field(
        default=0.0,
        description="Sum of capital allocated across all wheels",
    )
    total_positions_value: float = Field(
        default=0.0,
        description="Total value of current positions",
    )

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "name": "Primary Trading",
                "description": "Main wheel strategy portfolio",
                "default_capital": 50000.0,
                "created_at": "2026-01-31T10:00:00",
                "updated_at": "2026-01-31T10:00:00",
                "wheel_count": 10,
                "total_wheels": 10,
                "active_wheels": 8,
                "total_capital_allocated": 100000.0,
                "total_positions_value": 85000.0,
            }
        },
    }
