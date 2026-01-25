# OAuth Module Design Document
## Schwab API Integration for Covered Options Strategy System

**Version:** 1.0  
**Date:** January 22, 2026  
**Author:** Software Developer  
**Status:** Draft

---

## 1. Overview

### 1.1 Purpose

This document describes the design of an OAuth 2.0 module that enables the Covered Options Strategy System to securely connect to Charles Schwab's APIs. The module handles the complete OAuth lifecycle including initial authorization, token storage, automatic refresh, and secure API calls.

### 1.2 Background

The existing system uses API key authentication for Finnhub and Alpha Vantage. Schwab employs OAuth 2.0 with the Authorization Code Grant flow ("three-legged OAuth"), which requires:

1. User interaction via browser for initial authorization
2. A callback server to receive authorization codes
3. Token management for ongoing API access
4. Automatic token refresh before expiration

### 1.3 Goals

| Goal | Description |
|------|-------------|
| **Secure Authentication** | Implement OAuth 2.0 Authorization Code flow per Schwab specifications |
| **Minimal User Interaction** | After initial auth, operate unattended with automatic token refresh |
| **Simple Storage** | Store tokens in plaintext JSON (personal use, single-user system) |
| **Integration Ready** | Provide clean interface for Schwab API client module |
| **Resilient Operation** | Handle token expiration, network errors, and edge cases gracefully |

### 1.4 Non-Goals

- Multi-user/multi-tenant support
- Encrypted token storage (future enhancement)
- Web UI for OAuth management
- Mobile app support

---

## 2. Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           OAUTH MODULE                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────────────┐   │
│  │  Auth Server    │   │  Token Manager  │   │  Token Storage          │   │
│  │  (Flask)        │   │                 │   │  (JSON file)            │   │
│  │                 │   │                 │   │                         │   │
│  │  - /oauth/      │   │  - get_token()  │   │  - load()               │   │
│  │    callback     │   │  - refresh()    │   │  - save()               │   │
│  │  - /oauth/      │   │  - is_valid()   │   │  - ~/.schwab_tokens.json│   │
│  │    status       │   │  - revoke()     │   │                         │   │
│  └────────┬────────┘   └────────┬────────┘   └────────────┬────────────┘   │
│           │                     │                         │                 │
│           └─────────────────────┼─────────────────────────┘                 │
│                                 │                                           │
│                                 ▼                                           │
│                    ┌─────────────────────────┐                              │
│                    │   OAuth Coordinator     │                              │
│                    │                         │                              │
│                    │   - start_auth_flow()   │                              │
│                    │   - get_valid_token()   │                              │
│                    │   - ensure_authorized() │                              │
│                    └─────────────────────────┘                              │
│                                 │                                           │
└─────────────────────────────────┼───────────────────────────────────────────┘
                                  │
                                  ▼
                    ┌─────────────────────────┐
                    │   Schwab API Client     │
                    │   (uses OAuth tokens)   │
                    └─────────────────────────┘
```

### 2.2 Component Interactions

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                    INITIAL AUTHORIZATION FLOW                                 │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  User          CLI/App        Auth Server      Schwab OAuth      Browser     │
│   │               │               │                │                │        │
│   │  Run app      │               │                │                │        │
│   │──────────────>│               │                │                │        │
│   │               │               │                │                │        │
│   │               │ Start server  │                │                │        │
│   │               │──────────────>│                │                │        │
│   │               │               │                │                │        │
│   │               │ Generate auth URL              │                │        │
│   │               │───────────────────────────────>│                │        │
│   │               │                                │                │        │
│   │  Open URL     │                                │                │        │
│   │<──────────────│                                │                │        │
│   │               │                                │                │        │
│   │  Click link   │                                │                │        │
│   │───────────────────────────────────────────────────────────────>│        │
│   │               │                                │                │        │
│   │               │                                │  Login page    │        │
│   │               │                                │<───────────────│        │
│   │               │                                │                │        │
│   │  Enter credentials, select accounts           │                │        │
│   │───────────────────────────────────────────────>│                │        │
│   │               │                                │                │        │
│   │               │  Redirect with code            │                │        │
│   │               │<───────────────────────────────│                │        │
│   │               │               │                │                │        │
│   │               │ Receive code  │                │                │        │
│   │               │<──────────────│                │                │        │
│   │               │               │                │                │        │
│   │               │ Exchange code for tokens       │                │        │
│   │               │───────────────────────────────>│                │        │
│   │               │                                │                │        │
│   │               │ access_token + refresh_token   │                │        │
│   │               │<───────────────────────────────│                │        │
│   │               │               │                │                │        │
│   │               │ Save tokens   │                │                │        │
│   │               │──────────────>│ (to file)      │                │        │
│   │               │               │                │                │        │
│   │  Auth complete│               │                │                │        │
│   │<──────────────│               │                │                │        │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                    ONGOING API ACCESS FLOW                                    │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  App             Token Manager      Token Storage      Schwab API            │
│   │                   │                  │                 │                 │
│   │  get_valid_token()│                  │                 │                 │
│   │──────────────────>│                  │                 │                 │
│   │                   │                  │                 │                 │
│   │                   │  load()          │                 │                 │
│   │                   │─────────────────>│                 │                 │
│   │                   │                  │                 │                 │
│   │                   │  tokens          │                 │                 │
│   │                   │<─────────────────│                 │                 │
│   │                   │                  │                 │                 │
│   │                   │  Check expiry    │                 │                 │
│   │                   │  (if expired or  │                 │                 │
│   │                   │   near expiry)   │                 │                 │
│   │                   │                  │                 │                 │
│   │                   │  Refresh token   │                 │                 │
│   │                   │─────────────────────────────────────>│              │
│   │                   │                  │                 │                 │
│   │                   │  New tokens      │                 │                 │
│   │                   │<─────────────────────────────────────│              │
│   │                   │                  │                 │                 │
│   │                   │  save()          │                 │                 │
│   │                   │─────────────────>│                 │                 │
│   │                   │                  │                 │                 │
│   │  access_token     │                  │                 │                 │
│   │<──────────────────│                  │                 │                 │
│   │                   │                  │                 │                 │
│   │  API call with Bearer token          │                 │                 │
│   │──────────────────────────────────────────────────────────>│              │
│   │                   │                  │                 │                 │
│   │  Response         │                  │                 │                 │
│   │<──────────────────────────────────────────────────────────│              │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 File Structure

```
finnhub-options/
├── src/
│   ├── oauth/                      # NEW: OAuth module
│   │   ├── __init__.py
│   │   ├── config.py               # OAuth configuration
│   │   ├── auth_server.py          # Flask callback server
│   │   ├── token_manager.py        # Token lifecycle management
│   │   ├── token_storage.py        # File-based token persistence
│   │   └── coordinator.py          # High-level OAuth orchestration
│   │
│   ├── schwab/                     # NEW: Schwab API client
│   │   ├── __init__.py
│   │   ├── client.py               # HTTP client for Schwab APIs
│   │   ├── models.py               # Schwab-specific data models
│   │   └── endpoints.py            # API endpoint definitions
│   │
│   ├── config.py                   # Existing (add Schwab config)
│   ├── models.py                   # Existing
│   ├── finnhub_client.py           # Existing
│   ├── alphavantage_client.py      # Existing
│   ├── options_service.py          # Existing (integrate Schwab)
│   └── main.py                     # Existing
│
├── tests/
│   ├── oauth/                      # NEW: OAuth tests
│   │   ├── test_token_manager.py
│   │   ├── test_token_storage.py
│   │   └── test_coordinator.py
│   └── ...
│
├── scripts/                        # NEW: Utility scripts
│   ├── authorize_schwab_host.py    # HOST: One-time auth (HTTPS server)
│   └── check_schwab_auth.py        # CONTAINER: Check token status
│
├── .schwab_tokens.json             # NEW: Token storage (add to .gitignore)
│
└── config/                         # NEW: Configuration files
    └── schwab_oauth.example.json   # Example OAuth config
```

### 2.4 Container Architecture (Devcontainer Deployment)

**Critical Architectural Consideration**: This application runs inside a devcontainer, but the OAuth callback server must run on the host machine (requires SSL certificates and port 8443 access). This creates a split execution model.

#### Split Execution Model

```
┌─────────────────────────────────────────────────────────────────┐
│                         HOST MACHINE                             │
│                                                                  │
│  ┌────────────────────────────────────────────────┐             │
│  │  scripts/authorize_schwab_host.py              │             │
│  │  - Runs OAuth callback server (HTTPS)          │             │
│  │  - Access to /etc/letsencrypt SSL certificates │             │
│  │  - Listens on port 8443                        │             │
│  │  - Receives authorization code                 │             │
│  │  - Exchanges for tokens                        │             │
│  │  - Writes to PROJECT/.schwab_tokens.json       │             │
│  └────────────────────────────────────────────────┘             │
│                         │                                        │
│                         ▼                                        │
│           /workspaces/options_income/.schwab_tokens.json         │
│                         │ (workspace mount)                      │
└─────────────────────────┼──────────────────────────────────────┘
                          │
┌─────────────────────────┼──────────────────────────────────────┐
│                      DEVCONTAINER                   │            │
│                                                     │            │
│  /workspaces/options_income/.schwab_tokens.json ◄──┘            │
│                         │                                        │
│                         ▼                                        │
│  ┌────────────────────────────────────────────────┐             │
│  │  Main Application (wheel_strategy_tool)        │             │
│  │  - Reads tokens from workspace file            │             │
│  │  - Uses tokens for Schwab API calls            │             │
│  │  - Refreshes tokens when needed                │             │
│  │  - Writes updated tokens back to same file     │             │
│  └────────────────────────────────────────────────┘             │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

#### Token File Location Strategy

**Selected Approach: Project Directory (Option 1)**

Token file location: `/workspaces/options_income/.schwab_tokens.json`

**Rationale**:
- ✅ Workspace is already mounted in devcontainer
- ✅ Same absolute path in both host and container
- ✅ No additional mount configuration needed
- ✅ Simple path resolution (no context detection required)
- ⚠️ Must add to `.gitignore` to prevent token exposure

**Configuration**:
```python
# Default token file path in config.py
token_file: str = "/workspaces/options_income/.schwab_tokens.json"
```

**Alternative Considered: Home Directory**
- Token at `~/.schwab_tokens.json` (different paths in host/container)
- ❌ Requires explicit devcontainer mount configuration
- ❌ Path differs between contexts (needs detection logic)
- ❌ More complex setup

#### Execution Workflow

**First-Time Authorization** (runs on HOST):
1. Set environment variables on host: `SCHWAB_CLIENT_ID`, `SCHWAB_CLIENT_SECRET`
2. Run: `python scripts/authorize_schwab_host.py`
3. Script starts HTTPS server using host's SSL certificates
4. Browser opens for Schwab authorization
5. User logs in, grants access
6. Callback received, tokens exchanged
7. Tokens written to `/workspaces/options_income/.schwab_tokens.json`
8. Authorization complete

**Application Usage** (runs in CONTAINER):
1. Run: `wheel recommend NVDA --broker schwab`
2. Application reads tokens from `/workspaces/options_income/.schwab_tokens.json`
3. Token manager automatically refreshes if expired
4. Updated tokens written back to same file
5. API calls proceed with valid token

**Key Design Implications**:
- OAuth callback server code must be runnable standalone (outside container)
- Token storage must support shared file access (host writes, container reads/writes)
- Configuration must use absolute paths that work in both contexts
- Documentation must clearly specify which scripts run where
- No special path detection logic needed (same path everywhere)

#### Devcontainer Configuration

**Required `.devcontainer/devcontainer.json` entries**:

```json
{
  "mounts": [
    "source=/etc/letsencrypt,target=/etc/letsencrypt,type=bind,readonly"
  ]
}
```

**Note**: Workspace mount (`/workspaces/options_income`) is automatic; no additional mount needed for token file.

**`.gitignore` addition**:
```
# Schwab OAuth tokens (contains sensitive credentials)
.schwab_tokens.json
```

#### Security Considerations for Container Architecture

| Aspect | Implementation | Notes |
|--------|----------------|-------|
| Token File Permissions | Set by host script (chmod 600) | Container inherits permissions |
| File Locking | Not required | Single-user, sequential access |
| Path Exposure | Absolute path in code | Same in both contexts, no dynamic resolution |
| SSL Certificate Access | Mounted read-only from host | Container cannot modify certs |

---

## 3. Module Specifications

### 3.1 OAuth Configuration (`oauth/config.py`)

```python
from dataclasses import dataclass, field
from typing import Optional
import os


@dataclass
class SchwabOAuthConfig:
    """Configuration for Schwab OAuth 2.0."""

    # Required - from Schwab Dev Portal
    client_id: str
    client_secret: str

    # Callback configuration
    callback_host: str = "dirtydata.ai"
    callback_port: int = 8443
    callback_path: str = "/oauth/callback"

    # Schwab OAuth endpoints
    authorization_url: str = "https://api.schwabapi.com/v1/oauth/authorize"
    token_url: str = "https://api.schwabapi.com/v1/oauth/token"

    # Token storage (project directory for devcontainer compatibility)
    token_file: str = "/workspaces/options_income/.schwab_tokens.json"

    # SSL certificate paths (for callback server on HOST)
    ssl_cert_path: str = "/etc/letsencrypt/live/dirtydata.ai/fullchain.pem"
    ssl_key_path: str = "/etc/letsencrypt/live/dirtydata.ai/privkey.pem"

    # Token refresh settings
    refresh_buffer_seconds: int = 300  # Refresh 5 min before expiry
    
    @property
    def callback_url(self) -> str:
        """Full callback URL for OAuth redirect."""
        return f"https://{self.callback_host}:{self.callback_port}{self.callback_path}"
    
    @classmethod
    def from_env(cls) -> "SchwabOAuthConfig":
        """Load configuration from environment variables."""
        client_id = os.environ.get("SCHWAB_CLIENT_ID")
        client_secret = os.environ.get("SCHWAB_CLIENT_SECRET")
        
        if not client_id or not client_secret:
            raise ValueError(
                "Missing Schwab OAuth credentials. Set environment variables:\n"
                "  SCHWAB_CLIENT_ID=your_client_id\n"
                "  SCHWAB_CLIENT_SECRET=your_client_secret"
            )
        
        return cls(
            client_id=client_id,
            client_secret=client_secret,
            callback_host=os.environ.get("SCHWAB_CALLBACK_HOST", "dirtydata.ai"),
            callback_port=int(os.environ.get("SCHWAB_CALLBACK_PORT", "8443")),
            token_file=os.environ.get(
                "SCHWAB_TOKEN_FILE",
                "/workspaces/options_income/.schwab_tokens.json"
            ),
        )
```

### 3.2 Token Storage (`oauth/token_storage.py`)

```python
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TokenData:
    """Stored OAuth token data."""
    
    access_token: str
    refresh_token: str
    token_type: str  # "Bearer"
    expires_in: int  # seconds from issue
    scope: str
    issued_at: str  # ISO timestamp
    
    @property
    def expires_at(self) -> datetime:
        """Calculate expiration datetime."""
        issued = datetime.fromisoformat(self.issued_at)
        return issued + timedelta(seconds=self.expires_in)
    
    @property
    def is_expired(self) -> bool:
        """Check if access token is expired."""
        return datetime.now(timezone.utc) >= self.expires_at
    
    def expires_within(self, seconds: int) -> bool:
        """Check if token expires within given seconds."""
        buffer_time = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        return buffer_time >= self.expires_at
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "TokenData":
        """Create from dictionary."""
        return cls(**data)


class TokenStorage:
    """File-based token storage (plaintext JSON)."""
    
    def __init__(self, token_file: str):
        """
        Initialize token storage.
        
        Args:
            token_file: Path to token storage file
        """
        self.token_file = Path(token_file).expanduser()
        self._ensure_directory()
    
    def _ensure_directory(self) -> None:
        """Create parent directory if needed."""
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
    
    def save(self, token_data: TokenData) -> None:
        """
        Save tokens to file.
        
        Args:
            token_data: Token data to save
        """
        try:
            with open(self.token_file, "w") as f:
                json.dump(token_data.to_dict(), f, indent=2)
            logger.info(f"Tokens saved to {self.token_file}")
        except IOError as e:
            logger.error(f"Failed to save tokens: {e}")
            raise TokenStorageError(f"Failed to save tokens: {e}") from e
    
    def load(self) -> Optional[TokenData]:
        """
        Load tokens from file.
        
        Returns:
            TokenData if file exists and valid, None otherwise
        """
        if not self.token_file.exists():
            logger.debug("No token file found")
            return None
        
        try:
            with open(self.token_file, "r") as f:
                data = json.load(f)
            return TokenData.from_dict(data)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Invalid token file, will need re-authorization: {e}")
            return None
    
    def delete(self) -> bool:
        """
        Delete token file.
        
        Returns:
            True if deleted, False if didn't exist
        """
        if self.token_file.exists():
            self.token_file.unlink()
            logger.info("Token file deleted")
            return True
        return False
    
    def exists(self) -> bool:
        """Check if token file exists."""
        return self.token_file.exists()


class TokenStorageError(Exception):
    """Token storage operation failed."""
    pass
```

### 3.3 Token Manager (`oauth/token_manager.py`)

```python
import logging
import requests
from base64 import b64encode
from datetime import datetime, timezone
from typing import Optional

from .config import SchwabOAuthConfig
from .token_storage import TokenStorage, TokenData

logger = logging.getLogger(__name__)


class TokenManager:
    """Manages OAuth token lifecycle."""
    
    def __init__(self, config: SchwabOAuthConfig, storage: Optional[TokenStorage] = None):
        """
        Initialize token manager.
        
        Args:
            config: OAuth configuration
            storage: Token storage (creates default if not provided)
        """
        self.config = config
        self.storage = storage or TokenStorage(config.token_file)
        self._cached_token: Optional[TokenData] = None
    
    def exchange_code_for_tokens(self, authorization_code: str) -> TokenData:
        """
        Exchange authorization code for access and refresh tokens.
        
        Args:
            authorization_code: Code received from OAuth callback
            
        Returns:
            TokenData with access and refresh tokens
        """
        logger.info("Exchanging authorization code for tokens")
        
        # Prepare Basic auth header
        credentials = f"{self.config.client_id}:{self.config.client_secret}"
        auth_header = b64encode(credentials.encode()).decode()
        
        response = requests.post(
            self.config.token_url,
            headers={
                "Authorization": f"Basic {auth_header}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "authorization_code",
                "code": authorization_code,
                "redirect_uri": self.config.callback_url,
            },
            timeout=30,
        )
        
        if response.status_code != 200:
            logger.error(f"Token exchange failed: {response.status_code} - {response.text}")
            raise TokenExchangeError(f"Token exchange failed: {response.text}")
        
        data = response.json()
        
        token_data = TokenData(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            token_type=data.get("token_type", "Bearer"),
            expires_in=data["expires_in"],
            scope=data.get("scope", ""),
            issued_at=datetime.now(timezone.utc).isoformat(),
        )
        
        # Save tokens
        self.storage.save(token_data)
        self._cached_token = token_data
        
        logger.info("Successfully obtained and saved tokens")
        return token_data
    
    def refresh_tokens(self) -> TokenData:
        """
        Refresh access token using refresh token.
        
        Returns:
            New TokenData with fresh access token
        """
        current_token = self._get_current_token()
        if not current_token:
            raise TokenRefreshError("No refresh token available")
        
        logger.info("Refreshing access token")
        
        credentials = f"{self.config.client_id}:{self.config.client_secret}"
        auth_header = b64encode(credentials.encode()).decode()
        
        response = requests.post(
            self.config.token_url,
            headers={
                "Authorization": f"Basic {auth_header}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": current_token.refresh_token,
            },
            timeout=30,
        )
        
        if response.status_code != 200:
            logger.error(f"Token refresh failed: {response.status_code} - {response.text}")
            raise TokenRefreshError(f"Token refresh failed: {response.text}")
        
        data = response.json()
        
        token_data = TokenData(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", current_token.refresh_token),
            token_type=data.get("token_type", "Bearer"),
            expires_in=data["expires_in"],
            scope=data.get("scope", current_token.scope),
            issued_at=datetime.now(timezone.utc).isoformat(),
        )
        
        self.storage.save(token_data)
        self._cached_token = token_data
        
        logger.info("Successfully refreshed tokens")
        return token_data
    
    def get_valid_access_token(self) -> str:
        """
        Get a valid access token, refreshing if necessary.
        
        Returns:
            Valid access token string
            
        Raises:
            TokenNotAvailableError: If no valid token and can't refresh
        """
        token = self._get_current_token()
        
        if not token:
            raise TokenNotAvailableError(
                "No tokens available. Run authorization flow first."
            )
        
        # Check if refresh needed
        if token.expires_within(self.config.refresh_buffer_seconds):
            logger.info("Token expiring soon, refreshing...")
            token = self.refresh_tokens()
        
        return token.access_token
    
    def is_authorized(self) -> bool:
        """Check if we have valid (or refreshable) tokens."""
        token = self._get_current_token()
        return token is not None
    
    def get_token_status(self) -> dict:
        """Get current token status for diagnostics."""
        token = self._get_current_token()
        
        if not token:
            return {
                "authorized": False,
                "message": "No tokens stored"
            }
        
        return {
            "authorized": True,
            "expired": token.is_expired,
            "expires_at": token.expires_at.isoformat(),
            "expires_in_seconds": (token.expires_at - datetime.now(timezone.utc)).total_seconds(),
            "scope": token.scope,
        }
    
    def revoke(self) -> None:
        """Delete stored tokens (local revocation)."""
        self.storage.delete()
        self._cached_token = None
        logger.info("Tokens revoked (local)")
    
    def _get_current_token(self) -> Optional[TokenData]:
        """Get current token from cache or storage."""
        if self._cached_token:
            return self._cached_token
        
        self._cached_token = self.storage.load()
        return self._cached_token


class TokenExchangeError(Exception):
    """Failed to exchange authorization code for tokens."""
    pass


class TokenRefreshError(Exception):
    """Failed to refresh tokens."""
    pass


class TokenNotAvailableError(Exception):
    """No valid tokens available."""
    pass
```

### 3.4 Auth Server (`oauth/auth_server.py`)

```python
import logging
import ssl
import threading
import webbrowser
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import urlencode

from flask import Flask, request, Response
from werkzeug.serving import make_server

from .config import SchwabOAuthConfig

logger = logging.getLogger(__name__)


@dataclass
class AuthorizationResult:
    """Result of OAuth authorization flow."""
    success: bool
    authorization_code: Optional[str] = None
    error: Optional[str] = None
    error_description: Optional[str] = None


class OAuthCallbackServer:
    """
    Local HTTPS server to handle OAuth callback.
    
    This server runs temporarily during the OAuth flow to receive
    the authorization code from Schwab's redirect.
    """
    
    def __init__(self, config: SchwabOAuthConfig):
        """
        Initialize callback server.
        
        Args:
            config: OAuth configuration
        """
        self.config = config
        self.app = Flask(__name__)
        self.server: Optional[make_server] = None
        self.result: Optional[AuthorizationResult] = None
        self._shutdown_event = threading.Event()
        
        # Register callback route
        self.app.add_url_rule(
            self.config.callback_path,
            "oauth_callback",
            self._handle_callback,
            methods=["GET"]
        )
        
        # Status endpoint for debugging
        self.app.add_url_rule(
            "/oauth/status",
            "oauth_status",
            self._handle_status,
            methods=["GET"]
        )
    
    def _handle_callback(self) -> Response:
        """Handle OAuth callback from Schwab."""
        logger.info("Received OAuth callback")
        
        # Check for error response
        error = request.args.get("error")
        if error:
            error_desc = request.args.get("error_description", "Unknown error")
            logger.error(f"OAuth error: {error} - {error_desc}")
            self.result = AuthorizationResult(
                success=False,
                error=error,
                error_description=error_desc
            )
            self._shutdown_event.set()
            return Response(
                f"<html><body><h1>Authorization Failed</h1>"
                f"<p>Error: {error}</p><p>{error_desc}</p>"
                f"<p>You can close this window.</p></body></html>",
                status=400,
                content_type="text/html"
            )
        
        # Get authorization code
        code = request.args.get("code")
        if not code:
            logger.error("No authorization code in callback")
            self.result = AuthorizationResult(
                success=False,
                error="missing_code",
                error_description="No authorization code received"
            )
            self._shutdown_event.set()
            return Response(
                "<html><body><h1>Authorization Failed</h1>"
                "<p>No authorization code received.</p>"
                "<p>You can close this window.</p></body></html>",
                status=400,
                content_type="text/html"
            )
        
        logger.info("Authorization code received successfully")
        self.result = AuthorizationResult(
            success=True,
            authorization_code=code
        )
        self._shutdown_event.set()
        
        return Response(
            "<html><body><h1>Authorization Successful!</h1>"
            "<p>You can close this window and return to the application.</p>"
            "</body></html>",
            status=200,
            content_type="text/html"
        )
    
    def _handle_status(self) -> Response:
        """Status endpoint for debugging."""
        return Response(
            '{"status": "running", "waiting_for": "oauth_callback"}',
            status=200,
            content_type="application/json"
        )
    
    def generate_authorization_url(self) -> str:
        """Generate the Schwab authorization URL."""
        params = {
            "client_id": self.config.client_id,
            "redirect_uri": self.config.callback_url,
            "response_type": "code",
        }
        return f"{self.config.authorization_url}?{urlencode(params)}"
    
    def start(self) -> None:
        """Start the callback server."""
        # Create SSL context
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(
            self.config.ssl_cert_path,
            self.config.ssl_key_path
        )
        
        self.server = make_server(
            "0.0.0.0",  # Listen on all interfaces
            self.config.callback_port,
            self.app,
            ssl_context=ssl_context
        )
        
        logger.info(f"Starting OAuth callback server on port {self.config.callback_port}")
        
        # Run in background thread
        thread = threading.Thread(target=self.server.serve_forever)
        thread.daemon = True
        thread.start()
    
    def wait_for_callback(self, timeout: int = 300) -> AuthorizationResult:
        """
        Wait for OAuth callback.
        
        Args:
            timeout: Maximum seconds to wait
            
        Returns:
            AuthorizationResult
        """
        logger.info(f"Waiting for OAuth callback (timeout: {timeout}s)")
        
        if self._shutdown_event.wait(timeout=timeout):
            return self.result or AuthorizationResult(
                success=False,
                error="unknown",
                error_description="Server shutdown without result"
            )
        else:
            return AuthorizationResult(
                success=False,
                error="timeout",
                error_description=f"No callback received within {timeout} seconds"
            )
    
    def stop(self) -> None:
        """Stop the callback server."""
        if self.server:
            logger.info("Stopping OAuth callback server")
            self.server.shutdown()
            self.server = None


def run_authorization_flow(
    config: SchwabOAuthConfig,
    open_browser: bool = True,
    timeout: int = 300
) -> AuthorizationResult:
    """
    Run the complete OAuth authorization flow.
    
    Args:
        config: OAuth configuration
        open_browser: Whether to automatically open browser
        timeout: Seconds to wait for callback
        
    Returns:
        AuthorizationResult with authorization code or error
    """
    server = OAuthCallbackServer(config)
    
    try:
        # Start callback server
        server.start()
        
        # Generate and display authorization URL
        auth_url = server.generate_authorization_url()
        
        print("\n" + "=" * 60)
        print("SCHWAB OAUTH AUTHORIZATION")
        print("=" * 60)
        print("\nPlease authorize the application by visiting:")
        print(f"\n  {auth_url}\n")
        
        if open_browser:
            print("Opening browser automatically...")
            webbrowser.open(auth_url)
        else:
            print("Copy the URL above and paste it in your browser.")
        
        print("\nWaiting for authorization...")
        print("=" * 60 + "\n")
        
        # Wait for callback
        result = server.wait_for_callback(timeout)
        
        return result
        
    finally:
        server.stop()
```

### 3.5 OAuth Coordinator (`oauth/coordinator.py`)

```python
import logging
from typing import Optional

from .config import SchwabOAuthConfig
from .auth_server import run_authorization_flow, AuthorizationResult
from .token_manager import TokenManager, TokenNotAvailableError
from .token_storage import TokenStorage

logger = logging.getLogger(__name__)


class OAuthCoordinator:
    """
    High-level coordinator for OAuth operations.
    
    This is the main interface for the rest of the application.
    """
    
    def __init__(self, config: Optional[SchwabOAuthConfig] = None):
        """
        Initialize OAuth coordinator.
        
        Args:
            config: OAuth configuration (loads from env if not provided)
        """
        self.config = config or SchwabOAuthConfig.from_env()
        self.storage = TokenStorage(self.config.token_file)
        self.token_manager = TokenManager(self.config, self.storage)
    
    def ensure_authorized(self, auto_open_browser: bool = True) -> bool:
        """
        Ensure we have valid authorization, running flow if needed.
        
        Args:
            auto_open_browser: Whether to auto-open browser for auth
            
        Returns:
            True if authorized, False if authorization failed
        """
        # Check if already authorized
        if self.token_manager.is_authorized():
            logger.info("Already authorized")
            return True
        
        # Need to run authorization flow
        logger.info("No valid tokens, starting authorization flow")
        return self.run_authorization_flow(auto_open_browser)
    
    def run_authorization_flow(self, open_browser: bool = True) -> bool:
        """
        Run the OAuth authorization flow.
        
        Args:
            open_browser: Whether to automatically open browser
            
        Returns:
            True if successful, False otherwise
        """
        result = run_authorization_flow(
            self.config,
            open_browser=open_browser,
            timeout=300
        )
        
        if not result.success:
            logger.error(f"Authorization failed: {result.error} - {result.error_description}")
            return False
        
        # Exchange code for tokens
        try:
            self.token_manager.exchange_code_for_tokens(result.authorization_code)
            logger.info("Authorization successful!")
            return True
        except Exception as e:
            logger.error(f"Token exchange failed: {e}")
            return False
    
    def get_access_token(self) -> str:
        """
        Get a valid access token for API calls.
        
        Returns:
            Valid access token string
            
        Raises:
            TokenNotAvailableError: If not authorized
        """
        return self.token_manager.get_valid_access_token()
    
    def get_authorization_header(self) -> dict:
        """
        Get Authorization header for API requests.
        
        Returns:
            Dict with Authorization header
        """
        token = self.get_access_token()
        return {"Authorization": f"Bearer {token}"}
    
    def is_authorized(self) -> bool:
        """Check if currently authorized."""
        return self.token_manager.is_authorized()
    
    def get_status(self) -> dict:
        """Get current authorization status."""
        return self.token_manager.get_token_status()
    
    def revoke(self) -> None:
        """Revoke current authorization."""
        self.token_manager.revoke()
        logger.info("Authorization revoked")
```

---

## 4. Integration with Schwab API Client

### 4.1 Schwab Client Usage Pattern

```python
# Example usage in schwab/client.py

from src.oauth.coordinator import OAuthCoordinator


class SchwabClient:
    """Client for Schwab Trading and Market Data APIs."""
    
    def __init__(self, oauth: Optional[OAuthCoordinator] = None):
        self.oauth = oauth or OAuthCoordinator()
        self.base_url = "https://api.schwabapi.com"
        self.session = requests.Session()
    
    def _request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make authenticated request to Schwab API."""
        # Get fresh auth header (auto-refreshes if needed)
        headers = self.oauth.get_authorization_header()
        headers.update(kwargs.pop("headers", {}))
        
        url = f"{self.base_url}{endpoint}"
        
        response = self.session.request(
            method,
            url,
            headers=headers,
            **kwargs
        )
        
        # Handle 401 - token may have been revoked
        if response.status_code == 401:
            raise SchwabAuthenticationError("Authentication failed - re-authorize required")
        
        return response
    
    def get_accounts(self) -> dict:
        """Get linked accounts."""
        response = self._request("GET", "/v1/accounts")
        response.raise_for_status()
        return response.json()
    
    def get_option_chain(self, symbol: str) -> dict:
        """Get options chain for symbol."""
        response = self._request(
            "GET",
            "/v1/marketdata/chains",
            params={"symbol": symbol}
        )
        response.raise_for_status()
        return response.json()
```

---

## 5. Error Handling

### 5.1 Error Hierarchy

```python
class SchwabOAuthError(Exception):
    """Base exception for Schwab OAuth errors."""
    pass


class ConfigurationError(SchwabOAuthError):
    """OAuth configuration error."""
    pass


class AuthorizationError(SchwabOAuthError):
    """OAuth authorization flow error."""
    pass


class TokenExchangeError(SchwabOAuthError):
    """Failed to exchange authorization code."""
    pass


class TokenRefreshError(SchwabOAuthError):
    """Failed to refresh tokens."""
    pass


class TokenNotAvailableError(SchwabOAuthError):
    """No valid tokens available."""
    pass


class TokenStorageError(SchwabOAuthError):
    """Token storage operation failed."""
    pass
```

### 5.2 Error Recovery Strategy

| Error | Recovery Action |
|-------|-----------------|
| Token expired | Auto-refresh using refresh token |
| Refresh token invalid | Prompt user to re-authorize |
| Network error | Retry with exponential backoff |
| SSL certificate error | Check certificate paths, suggest renewal |
| Configuration missing | Clear error message with setup instructions |

---

## 6. Security Considerations

### 6.1 Current Implementation (Personal Use)

| Aspect | Implementation | Rationale |
|--------|----------------|-----------|
| Token Storage | Plaintext JSON | Single user, personal machine |
| File Permissions | User-only read/write | `chmod 600 ~/.schwab_tokens.json` |
| Client Secret | Environment variable | Not in code or config files |
| HTTPS | Required for callback | Schwab requirement + security |

### 6.2 Future Enhancements (If Needed)

For multi-user or more secure deployments:

- Encrypt tokens at rest using `cryptography` library
- Use system keychain (keyring library)
- Implement proper secret management (HashiCorp Vault, AWS Secrets Manager)
- Add token encryption key derived from user password

---

## 7. Testing Strategy

### 7.1 Unit Tests

| Module | Test Focus |
|--------|------------|
| `token_storage.py` | File I/O, JSON parsing, error handling |
| `token_manager.py` | Token refresh logic, expiry checking |
| `config.py` | Environment loading, validation |
| `coordinator.py` | Flow orchestration, state management |

### 7.2 Integration Tests

- Mock OAuth server for callback testing
- Token exchange simulation
- Full flow with test credentials (Schwab Sandbox)

### 7.3 Manual Testing Checklist

- [ ] Initial authorization flow completes
- [ ] Tokens are saved correctly
- [ ] Token refresh works before expiry
- [ ] Token refresh works after expiry
- [ ] API calls succeed with valid token
- [ ] Re-authorization works after revocation

---

## 8. Deployment Checklist

### 8.1 Prerequisites

- [ ] Let's Encrypt certificate for `dirtydata.ai` accessible at `/etc/letsencrypt`
- [ ] Port 8443 forwarded on router to host machine
- [ ] Schwab App registered with callback URL `https://dirtydata.ai:8443/oauth/callback`
- [ ] Devcontainer has SSL certificates mounted (already configured in `.devcontainer/devcontainer.json`)
- [ ] Environment variables set **on HOST**:
  - `SCHWAB_CLIENT_ID`
  - `SCHWAB_CLIENT_SECRET`

### 8.2 First-Time Setup (HOST Machine)

**Important**: Authorization must run on the HOST, not in the devcontainer.

```bash
# 1. Install dependencies ON HOST
pip install flask requests

# 2. Set environment variables ON HOST
export SCHWAB_CLIENT_ID="your_client_id"
export SCHWAB_CLIENT_SECRET="your_client_secret"

# 3. Navigate to project directory ON HOST
cd /workspaces/options_income

# 4. Run authorization script ON HOST
python scripts/authorize_schwab_host.py

# 5. Browser opens automatically for Schwab login
# Complete authorization in browser

# 6. Verify tokens saved
cat /workspaces/options_income/.schwab_tokens.json

# 7. Add to .gitignore if not already present
echo ".schwab_tokens.json" >> .gitignore
```

### 8.3 Application Usage (CONTAINER)

Once authorized, use the application normally **inside the devcontainer**:

```bash
# Inside devcontainer
wheel recommend NVDA --broker schwab
```

The application will:
1. Load tokens from `/workspaces/options_income/.schwab_tokens.json`
2. Auto-refresh before expiry (writes back to same file)
3. Make API calls with valid Bearer token

### 8.4 Token Management

**Token Location**: `/workspaces/options_income/.schwab_tokens.json`
- Written by host authorization script
- Read/refreshed by container application
- Same path in both contexts (workspace mount)

**Re-authorization needed if**:
- Refresh token expires (typically 7 days of inactivity)
- User revokes access in Schwab account settings
- Token file is deleted or corrupted

**To re-authorize**: Run `python scripts/authorize_schwab_host.py` again on HOST

### 8.5 Troubleshooting Container Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| "Token file not found" | Authorization not run | Run `authorize_schwab_host.py` on HOST |
| "Permission denied" writing tokens | File permissions | Check file ownership, run `chmod 600` on token file |
| "SSL certificate not found" | Missing mount | Verify `/etc/letsencrypt` mount in devcontainer.json |
| Token refresh fails | Network from container | Check container networking, verify Schwab API accessible |

---

## 9. Appendix

### A. Schwab OAuth URLs

| Purpose | URL |
|---------|-----|
| Authorization | `https://api.schwabapi.com/v1/oauth/authorize` |
| Token Exchange | `https://api.schwabapi.com/v1/oauth/token` |
| API Base | `https://api.schwabapi.com` |

### B. Token Lifetimes (Typical)

| Token Type | Lifetime |
|------------|----------|
| Access Token | 30 minutes |
| Refresh Token | 7 days |

*Note: Actual values may vary. Check Schwab documentation.*

### C. Required Python Packages

```
flask>=2.0.0
requests>=2.31.0
```

---

**Document History**

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-22 | Software Developer | Initial design |

---

**Document Approval**

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Tech Lead | | | |
| Security Review | | | |
