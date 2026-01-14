"""
Volatility calculation module for covered call strike optimization.

This module implements multiple volatility estimators following the formulas
specified in the PRD for strike optimization. All volatility values are
expressed as decimals (e.g., 0.25 = 25% annualized volatility).

Mathematical References:
- Close-to-Close: Standard historical volatility
- Parkinson: Uses daily high-low range (5.2x more efficient)
- Garman-Klass: Uses OHLC data (7.4x more efficient)
- Yang-Zhang: Handles overnight gaps (8.0x more efficient)
"""

import math
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration and Data Models
# ============================================================================


@dataclass
class VolatilityConfig:
    """
    Configuration for volatility calculations.

    Attributes:
        short_window: Lookback window for short-term volatility (default: 20 days)
        long_window: Lookback window for long-term volatility (default: 60 days)
        annualization_factor: Trading days per year (default: 252)
        min_data_points: Minimum data points required (default: 10)
    """
    short_window: int = 20
    long_window: int = 60
    annualization_factor: float = 252.0
    min_data_points: int = 10

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.short_window < 2:
            raise ValueError("short_window must be at least 2")
        if self.long_window < self.short_window:
            raise ValueError("long_window must be >= short_window")
        if self.annualization_factor <= 0:
            raise ValueError("annualization_factor must be positive")
        if self.min_data_points < 2:
            raise ValueError("min_data_points must be at least 2")


@dataclass
class BlendWeights:
    """
    Weights for blended volatility calculation.

    Attributes:
        realized_short: Weight for short-term realized vol (default: 0.30)
        realized_long: Weight for long-term realized vol (default: 0.20)
        implied: Weight for implied volatility (default: 0.50)
    """
    realized_short: float = 0.30
    realized_long: float = 0.20
    implied: float = 0.50

    def __post_init__(self) -> None:
        """Validate that weights sum to 1.0."""
        total = self.realized_short + self.realized_long + self.implied
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Weights must sum to 1.0, got {total:.4f}")

        if any(w < 0 for w in [self.realized_short, self.realized_long, self.implied]):
            raise ValueError("All weights must be non-negative")


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
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
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
            "metadata": self.metadata
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
    """
    dates: List[str]
    closes: List[float]
    opens: Optional[List[float]] = None
    highs: Optional[List[float]] = None
    lows: Optional[List[float]] = None
    volumes: Optional[List[int]] = None

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

        # Validate price data
        if any(c <= 0 for c in self.closes):
            raise ValueError("All prices must be positive")

        if self.highs and self.lows:
            for i in range(n):
                if self.highs[i] < self.lows[i]:
                    raise ValueError(f"High < Low at index {i}")


# ============================================================================
# Volatility Calculator
# ============================================================================


class VolatilityCalculator:
    """
    Calculate various volatility measures from price data.

    Implements multiple estimators:
    - Close-to-Close: Standard historical volatility
    - Parkinson: High-low range based (5.2x more efficient)
    - Garman-Klass: OHLC based (7.4x more efficient)
    - Yang-Zhang: Handles overnight gaps (8.0x more efficient)
    """

    def __init__(self, config: Optional[VolatilityConfig] = None):
        """
        Initialize volatility calculator.

        Args:
            config: Optional configuration. Uses defaults if not provided.
        """
        self.config = config or VolatilityConfig()
        logger.debug(f"VolatilityCalculator initialized with config: {self.config}")

    def calculate_close_to_close(
        self,
        prices: List[float],
        window: Optional[int] = None,
        annualize: bool = True,
        dates: Optional[List[str]] = None
    ) -> VolatilityResult:
        """
        Calculate close-to-close realized volatility.

        Formula: σ = sqrt((252 / (n-1)) * Σ(r_i - r_mean)²)
        where r_i = ln(P_i / P_{i-1})

        Args:
            prices: List of closing prices (oldest to newest)
            window: Lookback window in days (None = use all data)
            annualize: If True, multiply by √252
            dates: Optional dates for each price (ISO format)

        Returns:
            VolatilityResult with calculated volatility and metadata

        Raises:
            ValueError: If insufficient data points
        """
        window = window or self.config.short_window
        prices_window = prices[-window:] if len(prices) > window else prices

        if len(prices_window) < self.config.min_data_points:
            raise ValueError(
                f"Insufficient data: need at least {self.config.min_data_points} points, "
                f"got {len(prices_window)}"
            )

        # Calculate log returns
        log_returns = []
        for i in range(1, len(prices_window)):
            log_returns.append(math.log(prices_window[i] / prices_window[i-1]))

        # Calculate mean return
        mean_return = sum(log_returns) / len(log_returns)

        # Calculate variance
        variance = sum((r - mean_return) ** 2 for r in log_returns) / (len(log_returns) - 1)

        # Calculate volatility
        volatility = math.sqrt(variance)

        # Annualize if requested
        if annualize:
            volatility *= math.sqrt(self.config.annualization_factor)

        # Determine dates
        start_date = dates[-len(prices_window)] if dates else "unknown"
        end_date = dates[-1] if dates else "unknown"

        return VolatilityResult(
            volatility=volatility,
            method="close_to_close",
            window=window,
            data_points=len(prices_window),
            start_date=start_date,
            end_date=end_date,
            annualized=annualize,
            metadata={
                "returns_count": len(log_returns),
                "mean_return": mean_return,
                "efficiency_ratio": 1.0
            }
        )

    def calculate_parkinson(
        self,
        highs: List[float],
        lows: List[float],
        window: Optional[int] = None,
        annualize: bool = True,
        dates: Optional[List[str]] = None
    ) -> VolatilityResult:
        """
        Calculate Parkinson (high-low) volatility.

        Formula: σ = sqrt((252 / (4n * ln(2))) * Σln(H_i / L_i)²)

        More efficient than close-to-close (5.2x) as it uses more intraday information.

        Args:
            highs: List of daily high prices
            lows: List of daily low prices
            window: Lookback window in days
            annualize: If True, apply annualization
            dates: Optional dates for each price

        Returns:
            VolatilityResult with calculated volatility

        Raises:
            ValueError: If highs/lows length mismatch or insufficient data
        """
        if len(highs) != len(lows):
            raise ValueError("highs and lows must have same length")

        window = window or self.config.short_window
        highs_window = highs[-window:] if len(highs) > window else highs
        lows_window = lows[-window:] if len(lows) > window else lows

        if len(highs_window) < self.config.min_data_points:
            raise ValueError(f"Insufficient data: need at least {self.config.min_data_points} points")

        # Calculate Parkinson estimator
        sum_squared_log_hl = 0.0
        for h, l in zip(highs_window, lows_window):
            if h < l:
                raise ValueError(f"High ({h}) < Low ({l})")
            if l <= 0:
                raise ValueError("Prices must be positive")
            sum_squared_log_hl += math.log(h / l) ** 2

        n = len(highs_window)
        variance = sum_squared_log_hl / (4 * n * math.log(2))
        volatility = math.sqrt(variance)

        # Annualize if requested
        if annualize:
            volatility *= math.sqrt(self.config.annualization_factor)

        start_date = dates[-len(highs_window)] if dates else "unknown"
        end_date = dates[-1] if dates else "unknown"

        return VolatilityResult(
            volatility=volatility,
            method="parkinson",
            window=window,
            data_points=len(highs_window),
            start_date=start_date,
            end_date=end_date,
            annualized=annualize,
            metadata={
                "efficiency_ratio": 5.2,
                "uses_intraday": True
            }
        )

    def calculate_garman_klass(
        self,
        opens: List[float],
        highs: List[float],
        lows: List[float],
        closes: List[float],
        window: Optional[int] = None,
        annualize: bool = True,
        dates: Optional[List[str]] = None
    ) -> VolatilityResult:
        """
        Calculate Garman-Klass volatility.

        Formula: σ = sqrt((252/n) * Σ[0.5*ln(H/L)² - (2*ln(2)-1)*ln(C/O)²])

        Uses OHLC data for more efficient estimation (7.4x better than close-to-close).

        Args:
            opens: Opening prices
            highs: High prices
            lows: Low prices
            closes: Closing prices
            window: Lookback window in days
            annualize: If True, apply annualization
            dates: Optional dates

        Returns:
            VolatilityResult with calculated volatility
        """
        if not (len(opens) == len(highs) == len(lows) == len(closes)):
            raise ValueError("All OHLC arrays must have same length")

        window = window or self.config.short_window
        n = len(closes)
        opens_window = opens[-window:] if n > window else opens
        highs_window = highs[-window:] if n > window else highs
        lows_window = lows[-window:] if n > window else lows
        closes_window = closes[-window:] if n > window else closes

        if len(closes_window) < self.config.min_data_points:
            raise ValueError(f"Insufficient data: need at least {self.config.min_data_points} points")

        # Calculate Garman-Klass estimator
        sum_gk = 0.0
        for o, h, l, c in zip(opens_window, highs_window, lows_window, closes_window):
            if any(p <= 0 for p in [o, h, l, c]):
                raise ValueError("All prices must be positive")
            if h < l:
                raise ValueError(f"High ({h}) < Low ({l})")

            log_hl = math.log(h / l)
            log_co = math.log(c / o)
            sum_gk += 0.5 * log_hl ** 2 - (2 * math.log(2) - 1) * log_co ** 2

        n_points = len(closes_window)
        variance = sum_gk / n_points
        volatility = math.sqrt(variance)

        # Annualize if requested
        if annualize:
            volatility *= math.sqrt(self.config.annualization_factor)

        start_date = dates[-len(closes_window)] if dates else "unknown"
        end_date = dates[-1] if dates else "unknown"

        return VolatilityResult(
            volatility=volatility,
            method="garman_klass",
            window=window,
            data_points=n_points,
            start_date=start_date,
            end_date=end_date,
            annualized=annualize,
            metadata={
                "efficiency_ratio": 7.4,
                "uses_ohlc": True
            }
        )

    def calculate_yang_zhang(
        self,
        opens: List[float],
        highs: List[float],
        lows: List[float],
        closes: List[float],
        window: Optional[int] = None,
        annualize: bool = True,
        dates: Optional[List[str]] = None
    ) -> VolatilityResult:
        """
        Calculate Yang-Zhang volatility.

        Accounts for overnight jumps and is drift-independent.
        Most efficient estimator (8.0x) especially for stocks with significant gaps.

        Formula: σ_YZ = sqrt(σ_o² + k*σ_c² + (1-k)*σ_RS²)
        where k = 0.34 / (1.34 + (n+1)/(n-1))

        Args:
            opens: Opening prices
            highs: High prices
            lows: Low prices
            closes: Closing prices
            window: Lookback window in days
            annualize: If True, apply annualization
            dates: Optional dates

        Returns:
            VolatilityResult with calculated volatility
        """
        if not (len(opens) == len(highs) == len(lows) == len(closes)):
            raise ValueError("All OHLC arrays must have same length")

        window = window or self.config.short_window
        n = len(closes)
        opens_window = opens[-window:] if n > window else opens
        highs_window = highs[-window:] if n > window else highs
        lows_window = lows[-window:] if n > window else lows
        closes_window = closes[-window:] if n > window else closes

        if len(closes_window) < self.config.min_data_points:
            raise ValueError(f"Insufficient data: need at least {self.config.min_data_points} points")

        n_points = len(closes_window)

        # Calculate overnight returns (close-to-open)
        overnight_returns = []
        for i in range(1, n_points):
            overnight_returns.append(math.log(opens_window[i] / closes_window[i-1]))

        # Calculate open-to-close returns
        oc_returns = []
        for o, c in zip(opens_window, closes_window):
            oc_returns.append(math.log(c / o))

        # Calculate Rogers-Satchell component
        rs_sum = 0.0
        for o, h, l, c in zip(opens_window, highs_window, lows_window, closes_window):
            log_ho = math.log(h / o)
            log_lo = math.log(l / o)
            log_hc = math.log(h / c)
            log_lc = math.log(l / c)
            rs_sum += log_ho * log_hc + log_lo * log_lc

        # Calculate variance components
        overnight_mean = sum(overnight_returns) / len(overnight_returns)
        oc_mean = sum(oc_returns) / len(oc_returns)

        sigma_o_sq = sum((r - overnight_mean) ** 2 for r in overnight_returns) / (n_points - 1)
        sigma_c_sq = sum((r - oc_mean) ** 2 for r in oc_returns) / n_points
        sigma_rs_sq = rs_sum / n_points

        # Calculate Yang-Zhang parameter k
        k = 0.34 / (1.34 + (n_points + 1) / (n_points - 1))

        # Combine components
        variance = sigma_o_sq + k * sigma_c_sq + (1 - k) * sigma_rs_sq
        volatility = math.sqrt(variance)

        # Annualize if requested
        if annualize:
            volatility *= math.sqrt(self.config.annualization_factor)

        start_date = dates[-n_points] if dates else "unknown"
        end_date = dates[-1] if dates else "unknown"

        return VolatilityResult(
            volatility=volatility,
            method="yang_zhang",
            window=window,
            data_points=n_points,
            start_date=start_date,
            end_date=end_date,
            annualized=annualize,
            metadata={
                "efficiency_ratio": 8.0,
                "handles_gaps": True,
                "overnight_variance": sigma_o_sq,
                "oc_variance": sigma_c_sq,
                "rs_variance": sigma_rs_sq,
                "k_parameter": k
            }
        )

    def calculate_blended(
        self,
        price_data: PriceData,
        implied_volatility: float,
        weights: Optional[BlendWeights] = None
    ) -> VolatilityResult:
        """
        Calculate blended volatility estimate.

        Combines realized and implied volatility for forward-looking estimate.
        Default: 30% RV(20d) + 20% RV(60d) + 50% IV(ATM)

        Args:
            price_data: Historical price data
            implied_volatility: Implied volatility from ATM options (as decimal)
            weights: Optional custom weights (uses default if None)

        Returns:
            VolatilityResult with blended volatility
        """
        weights = weights or BlendWeights()

        # Calculate short-term realized vol
        rv_short = self.calculate_close_to_close(
            prices=price_data.closes,
            window=self.config.short_window,
            annualize=True,
            dates=price_data.dates
        )

        # Calculate long-term realized vol
        rv_long = self.calculate_close_to_close(
            prices=price_data.closes,
            window=self.config.long_window,
            annualize=True,
            dates=price_data.dates
        )

        # Blend volatilities
        blended_vol = (
            weights.realized_short * rv_short.volatility +
            weights.realized_long * rv_long.volatility +
            weights.implied * implied_volatility
        )

        return VolatilityResult(
            volatility=blended_vol,
            method="blended",
            window=self.config.long_window,
            data_points=len(price_data.closes),
            start_date=price_data.dates[0] if price_data.dates else "unknown",
            end_date=price_data.dates[-1] if price_data.dates else "unknown",
            annualized=True,
            metadata={
                "rv_short": rv_short.volatility,
                "rv_long": rv_long.volatility,
                "implied_vol": implied_volatility,
                "weights": {
                    "realized_short": weights.realized_short,
                    "realized_long": weights.realized_long,
                    "implied": weights.implied
                },
                "components": {
                    "rv_short_contribution": weights.realized_short * rv_short.volatility,
                    "rv_long_contribution": weights.realized_long * rv_long.volatility,
                    "implied_contribution": weights.implied * implied_volatility
                }
            }
        )

    def calculate_from_price_data(
        self,
        price_data: PriceData,
        method: str = "close_to_close",
        window: Optional[int] = None,
        annualize: bool = True
    ) -> VolatilityResult:
        """
        Calculate volatility from PriceData object using specified method.

        Convenience method that selects appropriate calculator based on available data.

        Args:
            price_data: Price data container
            method: Calculation method (close_to_close, parkinson, garman_klass, yang_zhang)
            window: Lookback window (None = use config default)
            annualize: Whether to annualize the result

        Returns:
            VolatilityResult

        Raises:
            ValueError: If method requires data not available in price_data
        """
        method = method.lower()

        if method == "close_to_close":
            return self.calculate_close_to_close(
                prices=price_data.closes,
                window=window,
                annualize=annualize,
                dates=price_data.dates
            )

        elif method == "parkinson":
            if price_data.highs is None or price_data.lows is None:
                raise ValueError("Parkinson method requires high and low prices")
            return self.calculate_parkinson(
                highs=price_data.highs,
                lows=price_data.lows,
                window=window,
                annualize=annualize,
                dates=price_data.dates
            )

        elif method == "garman_klass":
            if not all([price_data.opens, price_data.highs, price_data.lows]):
                raise ValueError("Garman-Klass method requires OHLC prices")
            return self.calculate_garman_klass(
                opens=price_data.opens,
                highs=price_data.highs,
                lows=price_data.lows,
                closes=price_data.closes,
                window=window,
                annualize=annualize,
                dates=price_data.dates
            )

        elif method == "yang_zhang":
            if not all([price_data.opens, price_data.highs, price_data.lows]):
                raise ValueError("Yang-Zhang method requires OHLC prices")
            return self.calculate_yang_zhang(
                opens=price_data.opens,
                highs=price_data.highs,
                lows=price_data.lows,
                closes=price_data.closes,
                window=window,
                annualize=annualize,
                dates=price_data.dates
            )

        else:
            raise ValueError(
                f"Unknown method: {method}. "
                f"Choose from: close_to_close, parkinson, garman_klass, yang_zhang"
            )
