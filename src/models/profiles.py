"""Risk profile enums for options strategies."""

from enum import Enum


class StrikeProfile(Enum):
    """
    Risk profile presets for strike selection.

    Each profile defines a target sigma range. The corresponding P(ITM)
    percentages are approximate and calibrated for typical 30-45 DTE options.

    IMPORTANT: P(ITM) is highly dependent on days to expiration (DTE).
    For short DTE (<14 days), the same sigma distance produces much lower
    P(ITM) because there's less time for the stock to move.
    """

    AGGRESSIVE = "aggressive"  # 0.5-1.0 sigma, ~30-40% P(ITM) at 30 DTE
    MODERATE = "moderate"  # 1.0-1.5 sigma, ~15-30% P(ITM) at 30 DTE
    CONSERVATIVE = "conservative"  # 1.5-2.0 sigma, ~7-15% P(ITM) at 30 DTE
    DEFENSIVE = "defensive"  # 2.0-2.5 sigma, ~2-7% P(ITM) at 30 DTE


# Sigma ranges for each profile (min_sigma, max_sigma)
PROFILE_SIGMA_RANGES: dict[StrikeProfile, tuple[float, float]] = {
    StrikeProfile.AGGRESSIVE: (0.5, 1.0),
    StrikeProfile.MODERATE: (1.0, 1.5),
    StrikeProfile.CONSERVATIVE: (1.5, 2.0),
    StrikeProfile.DEFENSIVE: (2.0, 2.5),
}


class DeltaBand(Enum):
    """
    Delta-band risk profiles for weekly covered call selection.

    Delta bands are the PRIMARY selector for weekly covered calls as they
    provide a direct measure of ITM probability/risk. Lower delta = lower
    assignment probability.

    These bands are calibrated for weekly options (5-14 DTE).
    """

    DEFENSIVE = "defensive"  # 0.05-0.10 delta, ~5-10% P(ITM)
    CONSERVATIVE = "conservative"  # 0.10-0.15 delta, ~10-15% P(ITM)
    MODERATE = "moderate"  # 0.15-0.25 delta, ~15-25% P(ITM)
    AGGRESSIVE = "aggressive"  # 0.25-0.35 delta, ~25-35% P(ITM)


# Delta ranges for each band (min_delta, max_delta)
DELTA_BAND_RANGES: dict[DeltaBand, tuple[float, float]] = {
    DeltaBand.DEFENSIVE: (0.05, 0.10),
    DeltaBand.CONSERVATIVE: (0.10, 0.15),
    DeltaBand.MODERATE: (0.15, 0.25),
    DeltaBand.AGGRESSIVE: (0.25, 0.35),
}
