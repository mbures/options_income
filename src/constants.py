"""
Shared constants for options analysis.

This module centralizes configuration values used across multiple modules,
making it easier to tune parameters and ensure consistency.
"""

# =============================================================================
# Liquidity Thresholds
# =============================================================================

MIN_OPEN_INTEREST = 100
"""Minimum open interest for tradeable contracts."""

MAX_BID_ASK_SPREAD_PCT = 10.0
"""Maximum bid-ask spread as percentage of mid price."""

MIN_BID_PRICE = 0.05
"""Minimum bid price to consider (filters out worthless options)."""


# =============================================================================
# Risk-Free Rate
# =============================================================================

DEFAULT_RISK_FREE_RATE = 0.05
"""Default risk-free rate for Black-Scholes calculations (5%)."""


# =============================================================================
# Strike Increments by Price Range
# =============================================================================

STRIKE_INCREMENTS: dict[tuple[float, float], float] = {
    (0, 5): 0.50,  # Stocks under $5: $0.50 increments
    (5, 25): 0.50,  # $5-$25: $0.50 increments
    (25, 200): 1.00,  # $25-$200: $1.00 increments
    (200, 500): 2.50,  # $200-$500: $2.50 increments
    (500, float("inf")): 5.00,  # Above $500: $5.00 increments
}
"""Standard strike price increments based on underlying price."""


# =============================================================================
# Delta Band Ranges for Weekly Selection
# =============================================================================

DELTA_BAND_RANGES: dict[str, tuple[float, float]] = {
    "defensive": (0.05, 0.10),  # ~5-10% P(ITM)
    "conservative": (0.10, 0.15),  # ~10-15% P(ITM)
    "moderate": (0.15, 0.25),  # ~15-25% P(ITM)
    "aggressive": (0.25, 0.35),  # ~25-35% P(ITM)
}
"""Delta ranges for weekly covered call risk profiles."""


# =============================================================================
# Allocation Weights for Ladder Strategies
# =============================================================================

ALLOCATION_WEIGHTS: dict[str, list[int]] = {
    "front_weighted": [4, 3, 2, 1],  # Near-term gets more contracts
    "back_weighted": [1, 2, 3, 4],  # Far-term gets more contracts
}
"""Relative weights for non-equal ladder allocation strategies."""


# =============================================================================
# Profile Sigma Ranges
# =============================================================================

PROFILE_SIGMA_RANGES: dict[str, tuple[float, float]] = {
    "aggressive": (0.5, 1.0),  # ~30-40% P(ITM) at 30 DTE
    "moderate": (1.0, 1.5),  # ~15-30% P(ITM) at 30 DTE
    "conservative": (1.5, 2.0),  # ~7-15% P(ITM) at 30 DTE
    "defensive": (2.0, 2.5),  # ~2-7% P(ITM) at 30 DTE
}
"""Sigma distance ranges for each risk profile."""
