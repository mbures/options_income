"""
Schwab API client module.

This module provides integration with Charles Schwab's Trading and Market Data APIs
using OAuth 2.0 authentication. It includes:

- SchwabClient: Authenticated HTTP client for API calls
- Market data endpoints: quotes, options chains
- Account data endpoints: accounts, positions
- Data models: SchwabAccount, SchwabPosition

Authentication is handled automatically via the OAuth module.
"""

from .client import SchwabClient
from .exceptions import SchwabAPIError, SchwabAuthenticationError
from .models import SchwabAccount, SchwabAccountBalances, SchwabPosition

__all__ = [
    "SchwabClient",
    "SchwabAPIError",
    "SchwabAuthenticationError",
    "SchwabAccount",
    "SchwabAccountBalances",
    "SchwabPosition",
]
