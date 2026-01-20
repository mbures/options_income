"""
Volatility data models.

This module contains the data structures used for volatility calculations
and price data representation.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class VolatilityResult:
    """
    Result of volatility calculation.

    Attributes:
        volatility: Annualized volatility as decimal (0.25 = 25%)
        method: Calculation method used
        window: Days used in calculation
        data_points: Actual data points used
        start_date: First date in window (ISO format)
        end_date: Last date in window (ISO format)
        annualized: Whether result is annualized
        metadata: Additional information about calculation
    """

    volatility: float
    method: str
    window: int
    data_points: int
    start_date: str
    end_date: str
    annualized: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "volatility": round(self.volatility, 4),
            "volatility_percent": round(self.volatility * 100, 2),
            "method": self.method,
            "window": self.window,
            "data_points": self.data_points,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "annualized": self.annualized,
            "metadata": self.metadata,
        }


@dataclass
class PriceData:
    """
    Price data container for volatility calculations.

    Attributes:
        dates: List of dates (ISO format strings)
        opens: Opening prices
        highs: High prices
        lows: Low prices
        closes: Closing prices
        volumes: Trading volumes (optional)
        adjusted_closes: Split/dividend adjusted closing prices (optional)
        dividends: Dividend amounts per day (0 if none) (optional)
        split_coefficients: Split ratios per day (1.0 if none) (optional)
    """

    dates: list[str]
    closes: list[float]
    opens: Optional[list[float]] = None
    highs: Optional[list[float]] = None
    lows: Optional[list[float]] = None
    volumes: Optional[list[int]] = None
    adjusted_closes: Optional[list[float]] = None
    dividends: Optional[list[float]] = None
    split_coefficients: Optional[list[float]] = None

    def __post_init__(self) -> None:
        """Validate data consistency."""
        n = len(self.dates)
        if len(self.closes) != n:
            raise ValueError("closes must match dates length")

        if self.opens is not None and len(self.opens) != n:
            raise ValueError("opens must match dates length")
        if self.highs is not None and len(self.highs) != n:
            raise ValueError("highs must match dates length")
        if self.lows is not None and len(self.lows) != n:
            raise ValueError("lows must match dates length")
        if self.volumes is not None and len(self.volumes) != n:
            raise ValueError("volumes must match dates length")
        if self.adjusted_closes is not None and len(self.adjusted_closes) != n:
            raise ValueError("adjusted_closes must match dates length")
        if self.dividends is not None and len(self.dividends) != n:
            raise ValueError("dividends must match dates length")
        if self.split_coefficients is not None and len(self.split_coefficients) != n:
            raise ValueError("split_coefficients must match dates length")

        # Validate price data
        if any(c <= 0 for c in self.closes):
            raise ValueError("All prices must be positive")

        if self.highs and self.lows:
            for i in range(n):
                if self.highs[i] < self.lows[i]:
                    raise ValueError(f"High < Low at index {i}")
