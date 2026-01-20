"""Data validation utilities."""

import logging
from collections.abc import Sequence

logger = logging.getLogger(__name__)


def validate_price_data(
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    symbol: str = "UNKNOWN",
) -> None:
    """
    Validate OHLC price data for consistency.

    Args:
        opens: Opening prices
        highs: High prices
        lows: Low prices
        closes: Closing prices
        symbol: Symbol for error messages

    Raises:
        ValueError: If data is invalid
    """
    if not (len(opens) == len(highs) == len(lows) == len(closes)):
        raise ValueError("Price arrays must have equal length")

    for i in range(len(opens)):
        if any(p <= 0 for p in [opens[i], highs[i], lows[i], closes[i]]):
            raise ValueError(f"Non-positive price detected at index {i} for {symbol}")

        if highs[i] < lows[i]:
            raise ValueError(f"High < Low at index {i} for {symbol}: {highs[i]} < {lows[i]}")

        if highs[i] / lows[i] > 1.5:
            logger.warning(
                f"Large intraday range at index {i} for {symbol}: "
                f"high={highs[i]}, low={lows[i]} ({highs[i] / lows[i]:.2f}x)"
            )
