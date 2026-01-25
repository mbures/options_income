"""
Schwab API endpoint definitions.

This module defines the API endpoints for Schwab's Trading and Market Data APIs.
Endpoint URLs are based on Schwab API documentation.

Documentation: https://developer.schwab.com/products/trader-api--individual
"""

# Market Data Endpoints
MARKETDATA_QUOTES = "/marketdata/v1/quotes"
MARKETDATA_QUOTE = "/marketdata/v1/{symbol}/quotes"
MARKETDATA_OPTION_CHAINS = "/marketdata/v1/chains"
MARKETDATA_OPTION_EXPIRATION = "/marketdata/v1/expirationchain"
MARKETDATA_MOVERS = "/marketdata/v1/movers/{symbol}"
MARKETDATA_MARKET_HOURS = "/marketdata/v1/markets"
MARKETDATA_INSTRUMENTS = "/marketdata/v1/instruments"

# Account & Trading Endpoints
ACCOUNTS = "/trader/v1/accounts"
ACCOUNT_DETAILS = "/trader/v1/accounts/{accountHash}"
ACCOUNT_POSITIONS = "/trader/v1/accounts/{accountHash}/positions"
ORDERS = "/trader/v1/accounts/{accountHash}/orders"
ORDER_DETAILS = "/trader/v1/accounts/{accountHash}/orders/{orderId}"

# User & Preference Endpoints
USER_PREFERENCE = "/trader/v1/userPreference"
