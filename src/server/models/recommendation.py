"""Pydantic models for Recommendation API requests and responses.

This module contains request and response schemas for recommendation endpoints,
including validation rules and examples.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class RecommendationRequest(BaseModel):
    """Request schema for generating recommendation.

    Attributes:
        expiration_date: Target expiration date (YYYY-MM-DD), optional

    Example:
        >>> RecommendationRequest(expiration_date="2026-03-21")
    """

    expiration_date: Optional[str] = Field(
        None, description="Target expiration date (YYYY-MM-DD)"
    )

    @field_validator("expiration_date")
    @classmethod
    def validate_date_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate date format and ensure it's in the future.

        Args:
            v: Date string to validate

        Returns:
            Validated date string or None

        Raises:
            ValueError: If date format is invalid or date is in the past
        """
        if v is not None:
            # Validate YYYY-MM-DD format
            try:
                date_obj = datetime.strptime(v, "%Y-%m-%d")
            except ValueError:
                raise ValueError(
                    "Invalid date format. Expected YYYY-MM-DD (e.g., 2026-03-21)"
                )

            # Validate future date
            if date_obj.date() <= datetime.now().date():
                raise ValueError("Expiration date must be in the future")

        return v

    model_config = {
        "json_schema_extra": {"example": {"expiration_date": "2026-03-21"}}
    }


class RecommendationResponse(BaseModel):
    """Response schema for recommendation data.

    Contains the recommendation for the next option trade based on current
    wheel state, profile, and market conditions.

    Attributes:
        wheel_id: Unique wheel identifier
        symbol: Stock ticker symbol
        current_state: Current wheel state
        direction: Recommended trade direction (put or call)
        strike: Recommended strike price
        expiration_date: Recommended expiration date
        premium_per_share: Premium per share for the option
        total_premium: Total premium for 1 contract
        probability_itm: Probability option expires in-the-money
        probability_otm: Probability option expires out-of-the-money
        annualized_return: Annualized return percentage
        days_to_expiry: Calendar days until expiration
        warnings: List of risk warnings
        has_warnings: Whether any warnings exist
        current_price: Current stock price
        volatility: Implied volatility
        profile: Strike selection profile
        recommended_at: Timestamp when recommendation was generated

    Example:
        >>> RecommendationResponse(
        >>>     wheel_id=1,
        >>>     symbol="AAPL",
        >>>     current_state="cash",
        >>>     direction="put",
        >>>     strike=145.0,
        >>>     expiration_date="2026-03-21"
        >>> )
    """

    # Wheel info
    wheel_id: int = Field(..., description="Unique wheel identifier")
    symbol: str = Field(..., description="Stock ticker symbol")
    current_state: str = Field(..., description="Current wheel state")

    # Recommendation
    direction: str = Field(..., description="Recommended trade direction (put/call)")
    strike: float = Field(..., description="Recommended strike price")
    expiration_date: str = Field(..., description="Recommended expiration date")
    premium_per_share: float = Field(..., description="Premium per share")
    total_premium: float = Field(..., description="Total premium for 1 contract")

    # Analysis
    probability_itm: float = Field(
        ..., description="Probability option expires in-the-money"
    )
    probability_otm: float = Field(
        ..., description="Probability option expires out-of-the-money"
    )
    annualized_return: Optional[float] = Field(
        None, description="Annualized return percentage"
    )
    days_to_expiry: int = Field(..., description="Calendar days until expiration")

    # Warnings
    warnings: list[str] = Field(default=[], description="List of risk warnings")
    has_warnings: bool = Field(default=False, description="Whether any warnings exist")

    # Metadata
    current_price: float = Field(..., description="Current stock price")
    volatility: float = Field(..., description="Implied volatility")
    profile: str = Field(..., description="Strike selection profile")
    recommended_at: datetime = Field(
        ..., description="Timestamp when recommendation was generated"
    )

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "wheel_id": 1,
                "symbol": "AAPL",
                "current_state": "cash",
                "direction": "put",
                "strike": 145.0,
                "expiration_date": "2026-03-21",
                "premium_per_share": 2.50,
                "total_premium": 250.0,
                "probability_itm": 0.15,
                "probability_otm": 0.85,
                "annualized_return": 24.5,
                "days_to_expiry": 30,
                "warnings": [],
                "has_warnings": False,
                "current_price": 150.0,
                "volatility": 0.28,
                "profile": "moderate",
                "recommended_at": "2026-02-01T10:00:00",
            }
        },
    }


class BatchRecommendationRequest(BaseModel):
    """Request schema for batch recommendations.

    Allows generating recommendations for multiple symbols in a single request.

    Attributes:
        symbols: List of stock ticker symbols
        expiration_date: Optional target expiration date for all
        profile: Optional profile override for all wheels

    Example:
        >>> BatchRecommendationRequest(
        >>>     symbols=["AAPL", "MSFT", "GOOGL"],
        >>>     expiration_date="2026-03-21"
        >>> )
    """

    symbols: list[str] = Field(
        ..., min_length=1, max_length=20, description="Stock symbols"
    )
    expiration_date: Optional[str] = Field(
        None, description="Target expiration date"
    )
    profile: Optional[str] = Field(None, description="Override profile for all")

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, v: list[str]) -> list[str]:
        """Validate and normalize symbol list.

        Args:
            v: List of symbols to validate

        Returns:
            List of uppercase, trimmed symbols

        Raises:
            ValueError: If any symbol is invalid
        """
        normalized = []
        for symbol in v:
            symbol = symbol.upper().strip()
            if not symbol.replace(".", "").replace("-", "").isalnum():
                raise ValueError(
                    f"Invalid symbol: {symbol}. Must be alphanumeric "
                    "(periods and hyphens allowed)"
                )
            normalized.append(symbol)
        return normalized

    @field_validator("expiration_date")
    @classmethod
    def validate_date_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate date format and ensure it's in the future.

        Args:
            v: Date string to validate

        Returns:
            Validated date string or None

        Raises:
            ValueError: If date format is invalid or date is in the past
        """
        if v is not None:
            # Validate YYYY-MM-DD format
            try:
                date_obj = datetime.strptime(v, "%Y-%m-%d")
            except ValueError:
                raise ValueError(
                    "Invalid date format. Expected YYYY-MM-DD (e.g., 2026-03-21)"
                )

            # Validate future date
            if date_obj.date() <= datetime.now().date():
                raise ValueError("Expiration date must be in the future")

        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "symbols": ["AAPL", "MSFT", "GOOGL"],
                "expiration_date": "2026-03-21",
                "profile": "moderate",
            }
        }
    }


class BatchRecommendationResponse(BaseModel):
    """Response schema for batch recommendations.

    Contains recommendations for multiple symbols along with any errors
    encountered during generation.

    Attributes:
        recommendations: List of successful recommendations
        errors: Dictionary mapping symbol to error message for failures
        requested_at: Timestamp when batch request was made

    Example:
        >>> BatchRecommendationResponse(
        >>>     recommendations=[...],
        >>>     errors={"INVALID": "Symbol not found"},
        >>>     requested_at=datetime.utcnow()
        >>> )
    """

    recommendations: list[RecommendationResponse] = Field(
        ..., description="List of successful recommendations"
    )
    errors: dict[str, str] = Field(
        default={}, description="Errors by symbol (symbol -> error message)"
    )
    requested_at: datetime = Field(..., description="Timestamp when request was made")

    model_config = {
        "json_schema_extra": {
            "example": {
                "recommendations": [
                    {
                        "wheel_id": 1,
                        "symbol": "AAPL",
                        "current_state": "cash",
                        "direction": "put",
                        "strike": 145.0,
                        "expiration_date": "2026-03-21",
                        "premium_per_share": 2.50,
                        "total_premium": 250.0,
                        "probability_itm": 0.15,
                        "probability_otm": 0.85,
                        "annualized_return": 24.5,
                        "days_to_expiry": 30,
                        "warnings": [],
                        "has_warnings": False,
                        "current_price": 150.0,
                        "volatility": 0.28,
                        "profile": "moderate",
                        "recommended_at": "2026-02-01T10:00:00",
                    }
                ],
                "errors": {"INVALID": "Symbol not found"},
                "requested_at": "2026-02-01T10:00:00",
            }
        },
    }
