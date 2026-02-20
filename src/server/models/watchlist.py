"""Pydantic models for Watchlist and Opportunity API requests and responses."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class WatchlistItemCreate(BaseModel):
    """Request schema for adding a symbol to the watchlist."""

    symbol: str = Field(..., description="Stock ticker symbol")
    notes: Optional[str] = Field(None, description="Optional notes about this symbol")

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, v: str) -> str:
        v = v.upper().strip()
        if not v or not v.replace(".", "").replace("-", "").isalnum():
            raise ValueError(
                f"Invalid symbol: {v}. Must be alphanumeric "
                "(periods and hyphens allowed)"
            )
        return v


class WatchlistItemResponse(BaseModel):
    """Response schema for a watchlist item."""

    id: int
    symbol: str
    notes: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class OpportunityResponse(BaseModel):
    """Response schema for a scanned opportunity."""

    id: int
    symbol: str
    direction: str
    profile: str
    strike: float
    expiration_date: str
    premium_per_share: float
    total_premium: float
    p_itm: float
    sigma_distance: float
    annualized_yield_pct: float
    bias_score: float
    dte: int
    current_price: float
    bid: float
    ask: float
    is_read: bool
    scanned_at: datetime

    model_config = {"from_attributes": True}


class OpportunityCountResponse(BaseModel):
    """Response schema for unread opportunity count."""

    unread_count: int


class ScanResultResponse(BaseModel):
    """Response schema for a scan operation result."""

    opportunities_found: int
    symbols_scanned: int
    errors: dict[str, str] = Field(default_factory=dict)
