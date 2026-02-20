"""Pydantic models for Position API requests and responses.

This module contains request and response schemas for position monitoring
endpoints, including validation rules and examples.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PositionStatusResponse(BaseModel):
    """Response schema for position status data.

    Provides real-time status for an open position including
    moneyness, risk assessment, and time decay metrics.

    Attributes:
        wheel_id: Associated wheel identifier
        trade_id: Associated trade identifier
        symbol: Stock ticker symbol
        direction: Option direction ("put" or "call")
        strike: Option strike price
        expiration_date: Expiration date (YYYY-MM-DD)
        dte_calendar: Calendar days to expiration
        dte_trading: Trading days to expiration
        current_price: Current stock price
        price_vs_strike: Signed distance from strike
        is_itm: Whether position is in the money
        is_otm: Whether position is out of the money
        moneyness_pct: Percentage distance from strike
        moneyness_label: Human-readable moneyness description
        risk_level: Risk level (LOW, MEDIUM, HIGH)
        risk_icon: Visual risk indicator
        risk_description: Human-readable risk description
        last_updated: Timestamp of status calculation
        premium_collected: Premium collected on trade
    """

    wheel_id: int = Field(..., description="Associated wheel identifier")
    trade_id: int = Field(..., description="Associated trade identifier")
    symbol: str = Field(..., description="Stock ticker symbol")
    direction: str = Field(..., description="Option direction (put or call)")
    strike: float = Field(..., description="Option strike price")
    expiration_date: str = Field(..., description="Expiration date (YYYY-MM-DD)")
    dte_calendar: int = Field(..., description="Calendar days to expiration")
    dte_trading: int = Field(..., description="Trading days to expiration")
    current_price: float = Field(..., description="Current stock price")
    price_vs_strike: float = Field(..., description="Signed distance from strike")
    is_itm: bool = Field(..., description="Whether position is in the money")
    is_otm: bool = Field(..., description="Whether position is out of the money")
    moneyness_pct: float = Field(..., description="Percentage distance from strike")
    moneyness_label: str = Field(
        ..., description="Human-readable moneyness description"
    )
    risk_level: str = Field(..., description="Risk level (LOW, MEDIUM, HIGH)")
    risk_icon: str = Field(..., description="Visual risk indicator")
    risk_description: str = Field(..., description="Human-readable risk description")
    last_updated: datetime = Field(..., description="Timestamp of status calculation")
    premium_collected: float = Field(..., description="Premium collected on trade")

    model_config = {
        "json_schema_extra": {
            "example": {
                "wheel_id": 1,
                "trade_id": 1,
                "symbol": "AAPL",
                "direction": "put",
                "strike": 150.0,
                "expiration_date": "2026-02-15",
                "dte_calendar": 14,
                "dte_trading": 10,
                "current_price": 155.50,
                "price_vs_strike": 5.50,
                "is_itm": False,
                "is_otm": True,
                "moneyness_pct": 3.67,
                "moneyness_label": "OTM by 3.7%",
                "risk_level": "LOW",
                "risk_icon": "🟢",
                "risk_description": "Low risk - OTM by 3.7%, comfortable margin",
                "last_updated": "2026-02-01T10:00:00",
                "premium_collected": 250.0,
            }
        }
    }


class PositionSummaryResponse(BaseModel):
    """Response schema for position summary listing.

    Provides a simplified view for listing multiple positions,
    including OHLC data and market state for dashboard display.

    Attributes:
        wheel_id: Associated wheel identifier
        trade_id: Associated trade identifier
        symbol: Stock ticker symbol
        direction: Option direction
        strike: Option strike price
        expiration_date: Expiration date
        dte_calendar: Calendar days to expiration
        current_price: Current stock price
        open_price: Day's opening price
        high_price: Day's high price
        low_price: Day's low price
        close_price: Previous close price
        moneyness_pct: Percentage distance from strike
        moneyness_label: Human-readable moneyness description
        market_open: Whether the market is currently open
        risk_level: Risk level
        risk_icon: Visual risk indicator
        premium_collected: Premium collected
    """

    wheel_id: int = Field(..., description="Associated wheel identifier")
    trade_id: int = Field(..., description="Associated trade identifier")
    symbol: str = Field(..., description="Stock ticker symbol")
    direction: str = Field(..., description="Option direction (put or call)")
    strike: float = Field(..., description="Option strike price")
    expiration_date: str = Field(..., description="Expiration date (YYYY-MM-DD)")
    dte_calendar: int = Field(..., description="Calendar days to expiration")
    current_price: float = Field(..., description="Current stock price")
    open_price: Optional[float] = Field(None, description="Day's opening price")
    high_price: Optional[float] = Field(None, description="Day's high price")
    low_price: Optional[float] = Field(None, description="Day's low price")
    close_price: Optional[float] = Field(None, description="Previous close price")
    moneyness_pct: float = Field(..., description="Percentage distance from strike")
    moneyness_label: str = Field(
        ..., description="Human-readable moneyness (e.g. OTM by 3.7%)"
    )
    market_open: bool = Field(
        False, description="Whether the US stock market is currently open"
    )
    risk_level: str = Field(..., description="Risk level (LOW, MEDIUM, HIGH)")
    risk_icon: str = Field(..., description="Visual risk indicator")
    premium_collected: float = Field(..., description="Premium collected on trade")

    model_config = {
        "json_schema_extra": {
            "example": {
                "wheel_id": 1,
                "trade_id": 1,
                "symbol": "AAPL",
                "direction": "put",
                "strike": 150.0,
                "expiration_date": "2026-02-15",
                "dte_calendar": 14,
                "current_price": 155.50,
                "open_price": 154.00,
                "high_price": 156.20,
                "low_price": 153.80,
                "close_price": 154.50,
                "moneyness_pct": 3.67,
                "moneyness_label": "OTM by 3.7%",
                "market_open": True,
                "risk_level": "LOW",
                "risk_icon": "🟢",
                "premium_collected": 250.0,
            }
        }
    }


class RiskAssessmentResponse(BaseModel):
    """Response schema for risk assessment.

    Provides focused risk view for a position.

    Attributes:
        wheel_id: Associated wheel identifier
        symbol: Stock ticker symbol
        risk_level: Risk level (LOW, MEDIUM, HIGH)
        risk_icon: Visual risk indicator
        risk_description: Human-readable risk description
        is_itm: Whether position is in the money
        moneyness_pct: Percentage distance from strike
        dte_calendar: Calendar days to expiration
        current_price: Current stock price
        strike: Option strike price
        direction: Option direction
    """

    wheel_id: int = Field(..., description="Associated wheel identifier")
    symbol: str = Field(..., description="Stock ticker symbol")
    risk_level: str = Field(..., description="Risk level (LOW, MEDIUM, HIGH)")
    risk_icon: str = Field(..., description="Visual risk indicator")
    risk_description: str = Field(..., description="Human-readable risk description")
    is_itm: bool = Field(..., description="Whether position is in the money")
    moneyness_pct: float = Field(..., description="Percentage distance from strike")
    dte_calendar: int = Field(..., description="Calendar days to expiration")
    current_price: float = Field(..., description="Current stock price")
    strike: float = Field(..., description="Option strike price")
    direction: str = Field(..., description="Option direction (put or call)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "wheel_id": 1,
                "symbol": "AAPL",
                "risk_level": "LOW",
                "risk_icon": "🟢",
                "risk_description": "Low risk - OTM by 3.7%, comfortable margin",
                "is_itm": False,
                "moneyness_pct": 3.67,
                "dte_calendar": 14,
                "current_price": 155.50,
                "strike": 150.0,
                "direction": "put",
            }
        }
    }


class BatchPositionResponse(BaseModel):
    """Response schema for batch position retrieval.

    Attributes:
        positions: List of position summaries
        total_count: Total number of positions
        high_risk_count: Count of high-risk positions
        medium_risk_count: Count of medium-risk positions
        low_risk_count: Count of low-risk positions
    """

    positions: list[PositionSummaryResponse] = Field(
        ..., description="List of position summaries"
    )
    total_count: int = Field(..., description="Total number of positions")
    high_risk_count: int = Field(..., description="Count of high-risk positions")
    medium_risk_count: int = Field(..., description="Count of medium-risk positions")
    low_risk_count: int = Field(..., description="Count of low-risk positions")

    model_config = {
        "json_schema_extra": {
            "example": {
                "positions": [
                    {
                        "wheel_id": 1,
                        "trade_id": 1,
                        "symbol": "AAPL",
                        "direction": "put",
                        "strike": 150.0,
                        "expiration_date": "2026-02-15",
                        "dte_calendar": 14,
                        "current_price": 155.50,
                        "moneyness_pct": 3.67,
                        "risk_level": "LOW",
                        "risk_icon": "🟢",
                        "premium_collected": 250.0,
                    }
                ],
                "total_count": 1,
                "high_risk_count": 0,
                "medium_risk_count": 0,
                "low_risk_count": 1,
            }
        }
    }
