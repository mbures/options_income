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

**Configuration Specification**:
- Configuration parameter `token_file` defaults to: "/workspaces/options_income/.schwab_tokens.json"
- Can be overridden via environment variable `SCHWAB_TOKEN_FILE`

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

Mount specification for SSL certificates:
- Source path: /etc/letsencrypt
- Target path: /etc/letsencrypt
- Type: bind mount
- Access mode: readonly

**Note**: Workspace mount (`/workspaces/options_income`) is automatic; no additional mount needed for token file.

**`.gitignore` addition**:

Entry to add:
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

**Purpose**: Central configuration for all OAuth-related settings and parameters.

**Data Structure: SchwabOAuthConfig**

Configuration data structure containing all OAuth parameters:

**Required Fields**:
- `client_id` (string): OAuth client ID from Schwab Developer Portal
- `client_secret` (string): OAuth client secret from Schwab Developer Portal

**Callback Configuration Fields**:
- `callback_host` (string): Domain name for OAuth callback (default: "dirtydata.ai")
- `callback_port` (integer): Port for callback server (default: 8443)
- `callback_path` (string): URL path for callback endpoint (default: "/oauth/callback")

**Schwab Endpoint Fields**:
- `authorization_url` (string): Schwab OAuth authorization endpoint (default: "https://api.schwabapi.com/v1/oauth/authorize")
- `token_url` (string): Schwab token exchange/refresh endpoint (default: "https://api.schwabapi.com/v1/oauth/token")

**Storage Configuration Fields**:
- `token_file` (string): Absolute path to token storage file (default: "/workspaces/options_income/.schwab_tokens.json")

**SSL Certificate Fields** (for HOST-side callback server):
- `ssl_cert_path` (string): Path to SSL certificate file (default: "/etc/letsencrypt/live/dirtydata.ai/fullchain.pem")
- `ssl_key_path` (string): Path to SSL private key file (default: "/etc/letsencrypt/live/dirtydata.ai/privkey.pem")

**Token Management Fields**:
- `refresh_buffer_seconds` (integer): Seconds before expiry to trigger refresh (default: 300, i.e., 5 minutes)

**Computed Properties**:
- `callback_url`: Constructs full callback URL from host, port, and path components

**Methods**:

1. **from_env() → SchwabOAuthConfig**
   - Loads configuration from environment variables
   - Required environment variables:
     - `SCHWAB_CLIENT_ID`: OAuth client ID
     - `SCHWAB_CLIENT_SECRET`: OAuth client secret
   - Optional environment variables (with defaults):
     - `SCHWAB_CALLBACK_HOST`: Override default callback host
     - `SCHWAB_CALLBACK_PORT`: Override default callback port
     - `SCHWAB_TOKEN_FILE`: Override default token file location
   - Raises error if required variables are missing
   - Returns configured instance with all settings populated

### 3.2 Token Storage (`oauth/token_storage.py`)

**Purpose**: Manages persistent storage and retrieval of OAuth tokens using JSON file storage.

**Data Structure: TokenData**

Represents OAuth token information with expiry tracking:

**Fields**:
- `access_token` (string): OAuth access token for API authentication
- `refresh_token` (string): OAuth refresh token for obtaining new access tokens
- `token_type` (string): Token type identifier (always "Bearer")
- `expires_in` (integer): Token lifetime in seconds from issue time
- `scope` (string): OAuth scope granted by authorization
- `issued_at` (string): ISO 8601 timestamp when token was issued

**Computed Properties**:
- `expires_at`: Calculates absolute expiration datetime by adding `expires_in` to `issued_at`
- `is_expired`: Boolean indicating if token is currently expired (compares current time to `expires_at`)

**Methods**:

1. **expires_within(seconds) → boolean**
   - Checks if token will expire within the specified number of seconds
   - Used to trigger proactive refresh before actual expiration
   - Returns true if expiration time is less than `seconds` away

2. **to_dict() → dictionary**
   - Converts token data to dictionary format for JSON serialization
   - Returns all fields as key-value pairs

3. **from_dict(data) → TokenData**
   - Creates TokenData instance from dictionary
   - Used when deserializing from JSON file
   - Validates required fields are present

**Class: TokenStorage**

Handles file-based persistence of token data:

**Initialization Parameters**:
- `token_file` (string): Absolute path to JSON file for token storage

**Internal State**:
- Expands tilde (~) in paths to user home directory
- Creates parent directories if they don't exist
- Stores Path object for file operations

**Methods**:

1. **save(token_data) → None**
   - Serializes TokenData to JSON format (indented for readability)
   - Writes to configured token file location
   - Logs successful save operations
   - Raises `TokenStorageError` on I/O failures (disk full, permissions, etc.)

2. **load() → TokenData or None**
   - Reads and deserializes token data from file
   - Returns None if file doesn't exist (first-time use)
   - Returns None if file is corrupted/invalid (logs warning)
   - Returns TokenData instance if successful
   - Handles JSON parse errors gracefully

3. **delete() → boolean**
   - Removes token file from filesystem
   - Returns True if file was deleted
   - Returns False if file didn't exist
   - Logs deletion operations

4. **exists() → boolean**
   - Checks if token file exists on filesystem
   - Used to determine if initial authorization is needed

**Exception: TokenStorageError**

Raised when file operations fail:
- Disk I/O errors
- Permission denied
- Filesystem full
- Path not accessible

### 3.3 Token Manager (`oauth/token_manager.py`)

**Purpose**: Manages the complete token lifecycle including exchange, refresh, validation, and caching.

**Class: TokenManager**

Orchestrates all token operations and maintains token state:

**Initialization Parameters**:
- `config` (SchwabOAuthConfig): OAuth configuration object
- `storage` (TokenStorage, optional): Token storage instance (creates default if not provided)

**Internal State**:
- Token cache for performance optimization
- Configuration reference
- Storage reference

**Methods**:

1. **exchange_code_for_tokens(authorization_code) → TokenData**
   - Exchanges authorization code for initial access and refresh tokens
   - Makes POST request to Schwab token endpoint
   - Authentication: HTTP Basic Auth using base64-encoded `client_id:client_secret`
   - Request parameters:
     - `grant_type`: "authorization_code"
     - `code`: The authorization code received
     - `redirect_uri`: Must match registered callback URL
   - Response handling:
     - Success (200): Parse JSON response, extract tokens
     - Failure: Log error, raise `TokenExchangeError`
   - Stores received tokens using TokenStorage
   - Updates internal cache
   - Returns TokenData with all token information

2. **refresh_tokens() → TokenData**
   - Refreshes expired or near-expiry access token using refresh token
   - Loads current token from storage
   - Makes POST request to Schwab token endpoint
   - Authentication: HTTP Basic Auth (same as exchange)
   - Request parameters:
     - `grant_type`: "refresh_token"
     - `refresh_token`: Current refresh token
   - Response handling:
     - Success: Extract new access token
     - May include new refresh token (if not, reuse existing)
     - Failure: Raise `TokenRefreshError`
   - Stores updated tokens
   - Returns new TokenData

3. **get_valid_access_token() → string**
   - Returns a currently valid access token for API use
   - Workflow:
     1. Load current token from cache or storage
     2. If no token exists, raise `TokenNotAvailableError`
     3. Check if token expires within buffer period (default: 5 minutes)
     4. If expiring soon, automatically refresh
     5. Return valid access token string
   - Ensures caller always gets usable token
   - Transparent automatic refresh

4. **is_authorized() → boolean**
   - Checks if valid tokens exist
   - Returns True if token file exists and is loadable
   - Does not validate expiration
   - Used for quick authorization status check

5. **get_token_status() → dictionary**
   - Returns diagnostic information about current token state
   - If unauthorized:
     - `authorized`: False
     - `message`: Explanation
   - If authorized:
     - `authorized`: True
     - `expired`: Boolean expiration status
     - `expires_at`: ISO timestamp of expiration
     - `expires_in_seconds`: Time remaining until expiration
     - `scope`: OAuth scope granted
   - Used for debugging and status displays

6. **revoke() → None**
   - Deletes stored tokens (local revocation only)
   - Clears internal cache
   - Does not notify Schwab (local operation)
   - Forces re-authorization on next use

**Private Methods**:

- **_get_current_token() → TokenData or None**
  - Returns token from cache if available
  - Otherwise loads from storage and caches
  - Returns None if no tokens exist

**Exceptions**:

- **TokenExchangeError**: Authorization code exchange failed
- **TokenRefreshError**: Token refresh request failed
- **TokenNotAvailableError**: No tokens available for use

### 3.4 Auth Server (`oauth/auth_server.py`)

**Purpose**: Provides temporary HTTPS server to receive OAuth callback and capture authorization code.

**Data Structure: AuthorizationResult**

Represents the outcome of an authorization flow:

**Fields**:
- `success` (boolean): Whether authorization succeeded
- `authorization_code` (string, optional): Code received from Schwab (on success)
- `error` (string, optional): Error code (on failure)
- `error_description` (string, optional): Human-readable error description (on failure)

**Class: OAuthCallbackServer**

Temporary HTTPS server for OAuth callback handling:

**Initialization Parameters**:
- `config` (SchwabOAuthConfig): OAuth configuration with callback settings

**Internal State**:
- Flask application instance
- HTTP server instance
- Authorization result storage
- Shutdown event for synchronization

**Server Endpoints**:

1. **GET /oauth/callback** (main callback endpoint)
   - Receives OAuth redirect from Schwab
   - Query parameters:
     - `code`: Authorization code (on success)
     - `error`: Error code (on failure)
     - `error_description`: Error details (on failure)
   - Response handling:
     - If error present: Set failure result, return HTML error page (400 status)
     - If code missing: Set missing code error, return HTML error page (400 status)
     - If code present: Set success result, return HTML success page (200 status)
   - All cases: Signal shutdown event to unblock waiting thread
   - Returns user-friendly HTML page indicating result

2. **GET /oauth/status** (diagnostic endpoint)
   - Returns JSON status indicating server is running
   - Used for debugging and health checks
   - Always returns 200 status

**Methods**:

1. **generate_authorization_url() → string**
   - Constructs Schwab authorization URL with proper parameters
   - Parameters included:
     - `client_id`: From configuration
     - `redirect_uri`: Full callback URL
     - `response_type`: Always "code" (authorization code flow)
   - Returns complete URL ready for browser

2. **start() → None**
   - Initializes HTTPS server with SSL certificates
   - SSL Configuration:
     - Loads certificate and private key from paths in config
     - Uses TLS server protocol
   - Network binding:
     - Listens on all interfaces (0.0.0.0)
     - Uses configured callback port
   - Execution:
     - Runs server in background daemon thread
     - Non-blocking operation

3. **wait_for_callback(timeout) → AuthorizationResult**
   - Blocks until callback received or timeout expires
   - Default timeout: 300 seconds (5 minutes)
   - Returns:
     - Success result with authorization code (if callback received)
     - Timeout error (if no callback within timeout period)
     - Unknown error (if server shutdown unexpectedly)

4. **stop() → None**
   - Gracefully shuts down HTTPS server
   - Cleans up server resources
   - Safe to call multiple times

**Function: run_authorization_flow**

High-level function orchestrating complete authorization flow:

**Parameters**:
- `config` (SchwabOAuthConfig): OAuth configuration
- `open_browser` (boolean, default True): Whether to auto-open browser
- `timeout` (integer, default 300): Seconds to wait for callback

**Workflow**:
1. Create and start callback server
2. Generate authorization URL
3. Display formatted instructions to user
4. Optionally open URL in default browser
5. Wait for callback with timeout
6. Return result (success or error)
7. Ensure server cleanup (in finally block)

**Console Output**:
- Banner with "SCHWAB OAUTH AUTHORIZATION"
- Full authorization URL for manual copying
- Browser opening notification (if applicable)
- Wait status indicator
- Formatted for clear user guidance

### 3.5 OAuth Coordinator (`oauth/coordinator.py`)

**Purpose**: High-level facade providing simple interface for OAuth operations. This is the primary integration point for the rest of the application.

**Class: OAuthCoordinator**

Coordinates all OAuth components to provide simple, unified interface:

**Initialization Parameters**:
- `config` (SchwabOAuthConfig, optional): OAuth configuration (loads from environment if not provided)

**Internal Components**:
- Configuration manager
- Token storage instance
- Token manager instance
- Automatic component wiring

**Public Methods**:

1. **ensure_authorized(auto_open_browser=True) → boolean**
   - Ensures application has valid authorization
   - Workflow:
     1. Check if already authorized (tokens exist)
     2. If authorized, return True immediately
     3. If not authorized, automatically trigger authorization flow
     4. Return success/failure status
   - Parameters:
     - `auto_open_browser`: Whether to automatically open browser for user
   - Use case: Call once at application startup to ensure API access
   - Non-blocking: Returns quickly if already authorized
   - User-friendly: Handles missing authorization transparently

2. **run_authorization_flow(open_browser=True) → boolean**
   - Explicitly runs the complete OAuth authorization flow
   - Workflow:
     1. Start callback server and generate authorization URL
     2. Display URL to user (optionally open browser)
     3. Wait for user to authorize in browser
     4. Receive authorization code via callback
     5. Exchange code for access and refresh tokens
     6. Save tokens to storage
   - Parameters:
     - `open_browser`: Whether to auto-open browser
   - Returns:
     - True if authorization succeeded
     - False if user denied, timeout, or exchange failed
   - Logs all errors for troubleshooting

3. **get_access_token() → string**
   - Returns valid access token for immediate API use
   - Automatically refreshes if token is expired or near expiration
   - Raises `TokenNotAvailableError` if no authorization exists
   - Transparent token refresh (caller doesn't need to handle expiry)
   - Primary method for obtaining tokens for API calls

4. **get_authorization_header() → dictionary**
   - Returns ready-to-use HTTP Authorization header
   - Format: `{"Authorization": "Bearer <token>"}`
   - Includes automatic token refresh
   - Convenience method for HTTP requests
   - Use case: Directly inject into requests headers

5. **is_authorized() → boolean**
   - Quick check for authorization status
   - Returns True if tokens exist (regardless of expiration)
   - Does not trigger authorization flow
   - Lightweight status check

6. **get_status() → dictionary**
   - Returns detailed authorization status information
   - Delegates to token manager's get_token_status()
   - Returns diagnostic data for debugging and display
   - Use case: Status dashboards, troubleshooting

7. **revoke() → None**
   - Revokes current authorization (deletes local tokens)
   - Forces re-authorization on next API call
   - Local operation only (does not notify Schwab)
   - Use case: Logout, token rotation, security cleanup

**Design Pattern**:
- Facade pattern: Simplifies complex OAuth subsystem
- Dependency injection: Accepts optional configuration
- Automatic wiring: Creates default components if not provided
- Error propagation: Bubbles up specific exceptions for caller handling

---

## 4. Integration with Schwab API Client

### 4.1 Schwab Client Usage Pattern

**Purpose**: Demonstrates how Schwab API client integrates with OAuth module.

**Class: SchwabClient** (implementation in `schwab/client.py`)

HTTP client for Schwab Trading and Market Data APIs with OAuth authentication:

**Initialization**:
- Parameters:
  - `oauth` (OAuthCoordinator, optional): OAuth coordinator instance (creates default if not provided)
- Internal state:
  - OAuth coordinator reference
  - Base URL for Schwab API: "https://api.schwabapi.com"
  - Requests session for connection pooling

**Private Methods**:

**_request(method, endpoint, **kwargs) → Response**
- Makes authenticated HTTP request to Schwab API
- Authentication workflow:
  1. Obtain authorization header from OAuth coordinator
  2. Merge with any additional headers from kwargs
  3. Construct full URL from base URL and endpoint
  4. Execute HTTP request with all parameters
  5. Check response status
  6. Handle 401 Unauthorized: Raise `SchwabAuthenticationError` indicating re-authorization needed
- Parameters:
  - `method`: HTTP method (GET, POST, etc.)
  - `endpoint`: API endpoint path (e.g., "/v1/accounts")
  - `kwargs`: Additional request parameters (query params, body, etc.)
- Returns: HTTP Response object
- Automatic token refresh: OAuth coordinator handles expiry transparently

**Public API Methods** (examples):

**get_accounts() → dictionary**
- Retrieves all linked brokerage accounts
- HTTP: GET /v1/accounts
- Returns: JSON response with account details
- Error handling: Raises HTTP errors if request fails

**get_option_chain(symbol) → dictionary**
- Retrieves options chain for specified symbol
- HTTP: GET /v1/marketdata/chains
- Parameters:
  - `symbol`: Stock ticker symbol
- Returns: JSON response with options chain data
- Error handling: Raises HTTP errors if request fails

**Integration Points**:
- OAuth coordinator provides authentication
- Client handles API-specific logic
- Separation of concerns: authentication vs. API operations
- Reusable pattern for all Schwab API endpoints

---

## 5. Error Handling

### 5.1 Error Hierarchy

**Purpose**: Provides specific exception types for different OAuth failure scenarios.

**Exception Classes**:

**SchwabOAuthError**
- Base exception for all Schwab OAuth-related errors
- Inherits from Python's Exception
- Allows catching all OAuth errors with single handler
- Use case: Top-level error handling in application

**ConfigurationError** (inherits from SchwabOAuthError)
- Raised when OAuth configuration is invalid or incomplete
- Scenarios:
  - Missing required environment variables (SCHWAB_CLIENT_ID, SCHWAB_CLIENT_SECRET)
  - Invalid configuration values
  - Inaccessible SSL certificate paths
- Use case: Application startup validation

**AuthorizationError** (inherits from SchwabOAuthError)
- Raised during OAuth authorization flow failures
- Scenarios:
  - User denies authorization
  - Invalid callback parameters
  - Authorization server errors
- Use case: User-facing authorization process

**TokenExchangeError** (inherits from SchwabOAuthError)
- Raised when authorization code cannot be exchanged for tokens
- Scenarios:
  - Invalid authorization code
  - Code already used or expired
  - Client credentials rejected
  - Network failures during exchange
- Use case: Initial authorization completion

**TokenRefreshError** (inherits from SchwabOAuthError)
- Raised when token refresh fails
- Scenarios:
  - Refresh token expired or revoked
  - Network failures during refresh
  - Client credentials changed
- Use case: Automatic token refresh operations

**TokenNotAvailableError** (inherits from SchwabOAuthError)
- Raised when attempting API call without valid tokens
- Scenarios:
  - No tokens stored (never authorized)
  - Tokens deleted or corrupted
  - Cannot refresh expired tokens
- Use case: Pre-flight authorization check

**TokenStorageError** (inherits from SchwabOAuthError)
- Raised when token file operations fail
- Scenarios:
  - Disk I/O errors
  - Permission denied
  - Filesystem full
  - Invalid JSON in token file
- Use case: File system operation failures

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

**Setup Steps**:

1. **Install Python dependencies on HOST**:
   - Required packages: flask, requests
   - Installation method: pip install

2. **Configure environment variables on HOST**:
   - Set `SCHWAB_CLIENT_ID` to your client ID from Schwab Developer Portal
   - Set `SCHWAB_CLIENT_SECRET` to your client secret from Schwab Developer Portal
   - Method: export command or shell configuration file

3. **Navigate to project directory**:
   - Change to: /workspaces/options_income

4. **Execute authorization script**:
   - Script: scripts/authorize_schwab_host.py
   - Execution context: HOST machine (not container)
   - Expected behavior: Starts HTTPS server, opens browser

5. **Complete browser authorization**:
   - Browser opens automatically to Schwab login page
   - User logs in with Schwab credentials
   - User selects accounts to authorize
   - Browser redirects back to local callback server
   - Server receives authorization code and exchanges for tokens

6. **Verify token storage**:
   - Check file exists: /workspaces/options_income/.schwab_tokens.json
   - File should contain JSON with access_token and refresh_token fields

7. **Update .gitignore**:
   - Add entry: .schwab_tokens.json
   - Prevents accidental commit of sensitive credentials

### 8.3 Application Usage (CONTAINER)

Once authorized, use the application normally **inside the devcontainer**.

**Example Command**:
- Command: wheel recommend NVDA --broker schwab
- Execution context: Inside devcontainer

**Application Workflow**:
1. **Token Loading**:
   - Reads tokens from `/workspaces/options_income/.schwab_tokens.json`
   - Parses JSON to extract access_token and refresh_token

2. **Token Refresh** (automatic):
   - Checks token expiration before each API call
   - If expiring within 5 minutes, automatically refreshes
   - Writes refreshed tokens back to same file
   - Transparent to user

3. **API Calls**:
   - Includes Bearer token in Authorization header
   - Makes authenticated requests to Schwab API
   - Retrieves account data, options chains, etc.

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

**Dependencies**:
- flask: Version 2.0.0 or higher (for HTTPS callback server)
- requests: Version 2.31.0 or higher (for OAuth token exchange and API calls)

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
