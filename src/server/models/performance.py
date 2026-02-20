"""Pydantic models for Performance API responses.

This module contains response schemas for wheel performance endpoints,
including period metrics and time-windowed P&L data.
"""

from typing import Optional

from pydantic import BaseModel, Field


class PeriodMetrics(BaseModel):
    """Metrics for a single time period.

    Attributes:
        option_premium_pnl: Net P&L from option premiums (after buyback costs)
        stock_pnl: P&L from completed wheel cycles (put assigned then call called away)
        total_pnl: Combined option premium and stock P&L
        trades_closed: Number of trades closed in the period
        contracts_traded: Total contracts across closed trades
        win_rate: Fraction of closed trades that were profitable (0.0 to 1.0)
    """

    option_premium_pnl: float = Field(..., description="Net P&L from option premiums")
    stock_pnl: float = Field(..., description="P&L from completed wheel cycles")
    total_pnl: float = Field(..., description="Combined option + stock P&L")
    trades_closed: int = Field(..., description="Number of trades closed in period")
    contracts_traded: int = Field(..., description="Total contracts traded")
    win_rate: float = Field(..., description="Win rate (0.0 to 1.0)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "option_premium_pnl": 1250.00,
                "stock_pnl": 500.00,
                "total_pnl": 1750.00,
                "trades_closed": 5,
                "contracts_traded": 8,
                "win_rate": 0.80,
            }
        }
    }


class PerformanceResponse(BaseModel):
    """Response schema for aggregate performance data across all wheels.

    Contains pre-computed P&L metrics across time windows, not tied to
    any specific wheel or symbol.

    Attributes:
        all_time: All-time performance metrics
        one_week: Performance metrics for the last 7 days
        one_month: Performance metrics for the last 30 days
        one_quarter: Performance metrics for the last 90 days
    """

    all_time: PeriodMetrics = Field(..., description="All-time performance metrics")
    one_week: PeriodMetrics = Field(..., description="Last 7 days")
    one_month: PeriodMetrics = Field(..., description="Last 30 days")
    one_quarter: PeriodMetrics = Field(..., description="Last 90 days")


class WheelPerformanceResponse(BaseModel):
    """Response schema for wheel performance data.

    Contains pre-computed P&L metrics across time windows for a single wheel.

    Attributes:
        wheel_id: Unique wheel identifier
        symbol: Stock ticker symbol
        all_time: All-time performance metrics
        one_week: Performance metrics for the last 7 days
        one_month: Performance metrics for the last 30 days
        one_quarter: Performance metrics for the last 90 days
    """

    wheel_id: int = Field(..., description="Unique wheel identifier")
    symbol: str = Field(..., description="Stock ticker symbol")
    all_time: PeriodMetrics = Field(..., description="All-time performance metrics")
    one_week: PeriodMetrics = Field(..., description="Last 7 days")
    one_month: PeriodMetrics = Field(..., description="Last 30 days")
    one_quarter: PeriodMetrics = Field(..., description="Last 90 days")

    model_config = {
        "json_schema_extra": {
            "example": {
                "wheel_id": 1,
                "symbol": "AAPL",
                "all_time": {
                    "option_premium_pnl": 5000.00,
                    "stock_pnl": 1200.00,
                    "total_pnl": 6200.00,
                    "trades_closed": 20,
                    "contracts_traded": 25,
                    "win_rate": 0.75,
                },
                "one_week": {
                    "option_premium_pnl": 250.00,
                    "stock_pnl": 0.00,
                    "total_pnl": 250.00,
                    "trades_closed": 1,
                    "contracts_traded": 1,
                    "win_rate": 1.0,
                },
                "one_month": {
                    "option_premium_pnl": 1000.00,
                    "stock_pnl": 500.00,
                    "total_pnl": 1500.00,
                    "trades_closed": 4,
                    "contracts_traded": 5,
                    "win_rate": 0.75,
                },
                "one_quarter": {
                    "option_premium_pnl": 3000.00,
                    "stock_pnl": 800.00,
                    "total_pnl": 3800.00,
                    "trades_closed": 12,
                    "contracts_traded": 15,
                    "win_rate": 0.83,
                },
            }
        }
    }
