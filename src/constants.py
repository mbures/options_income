"""
Application-wide constants.

This module defines constants used throughout the application to avoid
magic numbers and improve code maintainability.
"""

# Cache TTL (Time To Live) in seconds
CACHE_TTL_QUOTE_SECONDS = 300  # 5 minutes for real-time quotes
CACHE_TTL_OPTIONS_CHAIN_SECONDS = 900  # 15 minutes for options chains
CACHE_TTL_PRICE_HISTORY_SECONDS = 86400  # 24 hours for historical price data
CACHE_TTL_POSITION_STATUS_SECONDS = 300  # 5 minutes for position status

# Default lookback periods (in days)
DEFAULT_LOOKBACK_DAYS_SHORT = 30  # Short-term analysis (1 month)
DEFAULT_LOOKBACK_DAYS_MEDIUM = 60  # Medium-term analysis (2 months)
DEFAULT_LOOKBACK_DAYS_LONG = 252  # Long-term analysis (1 trading year)

# Position size limits
DEFAULT_SHARES_PER_CONTRACT = 100  # Standard options contract size
MAX_POSITION_SIZE_PERCENT = 10.0  # Maximum position size as % of portfolio

# Probability thresholds
MIN_PROBABILITY_ITM = 0.10  # 10% minimum ITM probability
MAX_PROBABILITY_ITM = 0.90  # 90% maximum ITM probability
DEFAULT_PROBABILITY_ITM = 0.30  # 30% default ITM probability

# Risk-free rate
DEFAULT_RISK_FREE_RATE = 0.05  # 5% annual risk-free rate

# Volatility defaults
DEFAULT_VOLATILITY = 0.20  # 20% annualized volatility
MIN_VOLATILITY = 0.05  # 5% minimum volatility
MAX_VOLATILITY = 2.00  # 200% maximum volatility

# Days in year (trading days vs calendar days)
TRADING_DAYS_PER_YEAR = 252
CALENDAR_DAYS_PER_YEAR = 365

# API retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY_SECONDS = 1.0
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30

# Date ranges for options screening
MIN_DAYS_TO_EXPIRY = 7  # Don't trade options with less than 1 week
MAX_DAYS_TO_EXPIRY = 365  # Don't trade options beyond 1 year
DEFAULT_DAYS_TO_EXPIRY = 30  # Default target: 30 days to expiration

# Performance thresholds
MIN_ANNUALIZED_YIELD_PERCENT = 5.0  # Minimum acceptable annualized yield
TARGET_ANNUALIZED_YIELD_PERCENT = 12.0  # Target annualized yield
HIGH_ANNUALIZED_YIELD_PERCENT = 20.0  # High yield threshold

# Warning thresholds
HIGH_OPPORTUNITY_COST_PERCENT = 5.0  # Warn if opportunity cost exceeds this
LOW_YIELD_THRESHOLD_PERCENT = 5.0  # Warn if yield below this

# Options filtering/quality thresholds
MAX_BID_ASK_SPREAD_PCT = 10.0  # Maximum bid-ask spread as percentage
MIN_OPEN_INTEREST = 100  # Minimum open interest for liquidity
MIN_BID_PRICE = 0.05  # Minimum bid price for option liquidity

# Strike price increments by price range (for rounding to tradeable strikes)
STRIKE_INCREMENTS = {
    (0, 5): 0.50,  # Stocks under $5: $0.50 increments
    (5, 25): 0.50,  # $5-$25: $0.50 increments
    (25, 200): 1.00,  # $25-$200: $1.00 increments
    (200, 500): 2.50,  # $200-$500: $2.50 increments
    (500, float('inf')): 5.00,  # Above $500: $5.00 increments
}
