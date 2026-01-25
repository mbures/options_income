# OAuth Module Requirements Document
## Schwab API Integration for Covered Options Strategy System

**Version:** 1.0  
**Date:** January 22, 2026  
**Author:** Software Developer + Stock Quant  
**Status:** Draft

---

## 1. Executive Summary

### 1.1 Purpose

This document defines the requirements for an OAuth 2.0 authentication module that enables the Covered Options Strategy System to securely access Charles Schwab's Trading and Market Data APIs. The module will handle the complete OAuth lifecycle for a single-user, personal-use deployment.

### 1.2 Business Context

The existing system uses Finnhub and Alpha Vantage for options and price data. Adding Schwab integration provides:

| Benefit | Description |
|---------|-------------|
| **Live Market Data** | Real-time quotes and options chains from user's actual broker |
| **Account Integration** | Access to positions, enabling automated covered call overlay scanning |
| **Data Quality** | Broker-sourced data often more reliable than third-party APIs |
| **Future Trading** | Foundation for eventual automated order placement |

### 1.3 Scope

**In Scope:**
- OAuth 2.0 Authorization Code flow implementation
- Local HTTPS callback server (runs on HOST machine)
- Token storage (plaintext JSON in project directory)
- Automatic token refresh (runs in devcontainer)
- Integration interface for Schwab API client
- Devcontainer architecture support with split execution model

**Out of Scope:**
- Multi-user support
- Encrypted token storage
- Web-based OAuth management UI
- Schwab API client implementation (separate module)
- Order placement functionality
- Container orchestration (Docker Compose, Kubernetes)

### 1.4 Key Stakeholders

| Role | Responsibility |
|------|----------------|
| User (You) | Authorize access, use system for options analysis |
| System | Maintain valid tokens, make authenticated API calls |
| Schwab | Provide OAuth infrastructure, validate tokens |

---

## 2. Functional Requirements

### 2.1 Configuration Management

**FR-O1: Environment-Based Configuration**
- System MUST load OAuth credentials from environment variables:
  - `SCHWAB_CLIENT_ID` (required)
  - `SCHWAB_CLIENT_SECRET` (required)
  - `SCHWAB_CALLBACK_HOST` (optional, default: `dirtydata.ai`)
  - `SCHWAB_CALLBACK_PORT` (optional, default: `8443`)
  - `SCHWAB_TOKEN_FILE` (optional, default: `~/.schwab_tokens.json`)
- System MUST fail with clear error message if required variables missing

**FR-O2: Configuration Validation**
- System MUST validate that client_id and client_secret are non-empty strings
- System MUST validate that callback_port is a valid port number (1-65535)
- System MUST validate that SSL certificate files exist at configured paths

**FR-O3: Callback URL Generation**
- System MUST generate callback URL in format: `https://{host}:{port}/oauth/callback`
- Generated URL MUST match the URL registered in Schwab Dev Portal

**FR-O3.1: Container Architecture Support** (NEW)
- Token file MUST use project directory path: `/workspaces/options_income/.schwab_tokens.json`
- Path MUST be absolute and work identically in both host and container contexts
- Authorization script MUST be runnable on host (outside container)
- Application in container MUST successfully read and refresh tokens from shared file
- Token file MUST be added to `.gitignore` to prevent credential exposure

### 2.2 Authorization Flow

**FR-O4: Authorization URL Generation**
- System MUST generate valid Schwab authorization URL with parameters:
  - `client_id`: From configuration
  - `redirect_uri`: Callback URL
  - `response_type`: "code"

**FR-O5: Callback Server**
- System MUST start HTTPS server on configured port **on HOST machine**
- Server MUST use valid SSL certificate for configured domain (from `/etc/letsencrypt`)
- Server MUST handle GET requests to `/oauth/callback`
- Server MUST extract `code` parameter from callback
- Server MUST handle `error` and `error_description` parameters
- Server MUST display user-friendly success/failure HTML page
- Server MUST write tokens to project directory (accessible to container)

**FR-O6: Browser Integration**
- System SHOULD automatically open authorization URL in default browser
- System MUST display authorization URL in console for manual copy
- System MUST wait for callback with configurable timeout (default: 5 minutes)

**FR-O7: Authorization Code Exchange**
- System MUST exchange authorization code for tokens via POST to token endpoint
- Request MUST include:
  - `grant_type`: "authorization_code"
  - `code`: Authorization code from callback
  - `redirect_uri`: Same callback URL used in authorization
- Request MUST use Basic authentication with client_id:client_secret
- System MUST parse response for `access_token`, `refresh_token`, `expires_in`

### 2.3 Token Management

**FR-O8: Token Storage**
- System MUST store tokens in JSON file at configured path: `/workspaces/options_income/.schwab_tokens.json`
- Stored data MUST include:
  - `access_token`
  - `refresh_token`
  - `token_type`
  - `expires_in`
  - `scope`
  - `issued_at` (ISO timestamp)
- System MUST create parent directories if they don't exist
- Token file MUST be writable from both host (authorization) and container (refresh)
- File permissions SHOULD be set to 600 (user-only read/write)

**FR-O9: Token Loading**
- System MUST load tokens from storage file on startup
- System MUST handle missing file gracefully (no tokens available)
- System MUST handle corrupted file gracefully (treat as no tokens)

**FR-O10: Token Expiry Checking**
- System MUST calculate token expiration from `issued_at` + `expires_in`
- System MUST provide method to check if token is expired
- System MUST provide method to check if token expires within N seconds

**FR-O11: Automatic Token Refresh**
- System MUST refresh tokens before they expire (configurable buffer, default: 5 minutes)
- Refresh request MUST include:
  - `grant_type`: "refresh_token"
  - `refresh_token`: Current refresh token
- System MUST update stored tokens after successful refresh
- System MUST preserve refresh_token if not returned in refresh response

**FR-O12: Token Access Interface**
- System MUST provide method to get valid access token
- Method MUST automatically refresh if token expired or near-expiry
- Method MUST raise clear exception if no tokens and can't refresh
- System MUST provide method to get complete Authorization header

### 2.4 Status and Diagnostics

**FR-O13: Authorization Status**
- System MUST provide method to check if currently authorized
- System MUST provide token status including:
  - Whether authorized
  - Whether token is expired
  - When token expires
  - Seconds until expiration
  - Token scope

**FR-O14: Logging**
- System MUST log all significant events:
  - Authorization flow start/success/failure
  - Token refresh attempts and results
  - Token storage operations
  - Error conditions
- Log level SHOULD be configurable

### 2.5 Revocation and Cleanup

**FR-O15: Local Revocation**
- System MUST provide method to delete stored tokens
- Deletion MUST clear any cached tokens in memory
- System SHOULD log revocation event

### 2.6 Container Architecture Requirements (NEW)

**FR-O16: Split Execution Model**
- Authorization script MUST be executable on host machine (outside devcontainer)
- Authorization script MUST have access to SSL certificates at `/etc/letsencrypt`
- Authorization script MUST write tokens to workspace directory
- Application in container MUST read tokens from same workspace directory
- Token refresh MUST work from inside container
- No runtime container detection logic required (same path everywhere)

**FR-O17: Devcontainer Integration**
- Token file path MUST be: `/workspaces/options_income/.schwab_tokens.json`
- Path MUST work identically on host and in container
- No additional volume mounts required beyond workspace (automatic)
- SSL certificate mount MUST be configured in `.devcontainer/devcontainer.json`
- Documentation MUST clearly specify which operations run where (host vs container)

**FR-O18: File Access Patterns**
- Host authorization script: Write-only access to token file
- Container application: Read/write access to token file (for refresh)
- No file locking mechanism required (single-user, sequential access)
- Token file MUST be excluded from version control (`.gitignore`)

---

## 3. Non-Functional Requirements

### 3.1 Performance

**NFR-O1: Server Startup Time**
- Callback server MUST start within 2 seconds

**NFR-O2: Token Operations**
- Token load from file: < 50ms
- Token save to file: < 100ms
- Token refresh API call: < 5 seconds (network dependent)

**NFR-O3: Memory Usage**
- OAuth module MUST use < 10MB memory

### 3.2 Reliability

**NFR-O4: Network Resilience**
- Token refresh MUST retry on transient network errors (up to 3 attempts)
- Retry MUST use exponential backoff (1s, 2s, 4s)

**NFR-O5: Graceful Degradation**
- System MUST continue operating if token refresh fails temporarily
- System MUST provide clear error when re-authorization is required

**NFR-O6: Crash Recovery**
- Tokens MUST persist across application restarts
- Incomplete token writes MUST NOT corrupt existing tokens

### 3.3 Security

**NFR-O7: Credential Handling**
- Client secret MUST NOT be logged
- Client secret MUST NOT appear in error messages
- Client secret MUST NOT be stored in code or config files

**NFR-O8: Token Protection**
- Token file SHOULD have restricted permissions (user-only read/write)
- Access tokens MUST NOT be logged in full (truncate in logs)

**NFR-O9: HTTPS Required**
- Callback server MUST use HTTPS with valid certificate
- All Schwab API communication MUST use HTTPS

**NFR-O10: No Token in URLs**
- Access tokens MUST NOT appear in URL query parameters
- Access tokens MUST only be sent in Authorization header

### 3.4 Usability

**NFR-O11: Clear Error Messages**
- All errors MUST include actionable guidance
- Configuration errors MUST specify which variable is missing/invalid
- Authorization failures MUST suggest re-running auth flow

**NFR-O12: Minimal User Interaction**
- After initial authorization, system MUST operate without user input
- User SHOULD only need to interact during initial auth and re-auth

### 3.5 Maintainability

**NFR-O13: Code Quality**
- Code MUST follow PEP 8 style guidelines
- All public functions MUST have docstrings
- All functions MUST have type hints
- Ruff linting score MUST be clean (no errors)

**NFR-O14: Testing**
- Unit test coverage MUST be > 80%
- All error paths MUST have test coverage
- Mock external services in tests (no real API calls)

**NFR-O15: Documentation**
- Module MUST have README with setup instructions
- All configuration options MUST be documented
- Common errors MUST have troubleshooting guide

### 3.6 Compatibility

**NFR-O16: Python Version**
- Module MUST support Python 3.9+

**NFR-O17: Dependencies**
- Module SHOULD minimize external dependencies
- Required: `flask`, `requests`
- Optional: None

**NFR-O18: Platform Support**
- Module MUST work on Linux (primary)
- Module SHOULD work on macOS
- Module MAY work on Windows (not tested)

---

## 4. Technical Specifications

### 4.1 Schwab OAuth Endpoints

| Endpoint | URL | Method |
|----------|-----|--------|
| Authorization | `https://api.schwabapi.com/v1/oauth/authorize` | GET (browser) |
| Token Exchange | `https://api.schwabapi.com/v1/oauth/token` | POST |
| Token Refresh | `https://api.schwabapi.com/v1/oauth/token` | POST |

### 4.2 Token Exchange Request

```http
POST /v1/oauth/token HTTP/1.1
Host: api.schwabapi.com
Authorization: Basic {base64(client_id:client_secret)}
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code={code}&redirect_uri={callback_url}
```

### 4.3 Token Refresh Request

```http
POST /v1/oauth/token HTTP/1.1
Host: api.schwabapi.com
Authorization: Basic {base64(client_id:client_secret)}
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token={refresh_token}
```

### 4.4 Token Response Structure

```json
{
  "access_token": "string",
  "refresh_token": "string",
  "token_type": "Bearer",
  "expires_in": 1800,
  "scope": "PlaceTrades AccountAccess MoveMoney"
}
```

### 4.5 Token Storage Format

```json
{
  "access_token": "eyJ...",
  "refresh_token": "xyz...",
  "token_type": "Bearer",
  "expires_in": 1800,
  "scope": "PlaceTrades AccountAccess MoveMoney",
  "issued_at": "2026-01-22T10:30:00+00:00"
}
```

### 4.6 Configuration Structure

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `client_id` | str | Yes | - | Schwab App client ID |
| `client_secret` | str | Yes | - | Schwab App client secret |
| `callback_host` | str | No | dirtydata.ai | Callback domain |
| `callback_port` | int | No | 8443 | Callback server port |
| `callback_path` | str | No | /oauth/callback | Callback URL path |
| `token_file` | str | No | /workspaces/options_income/.schwab_tokens.json | Token storage path (container-compatible) |
| `ssl_cert_path` | str | No | /etc/letsencrypt/live/dirtydata.ai/fullchain.pem | SSL certificate |
| `ssl_key_path` | str | No | /etc/letsencrypt/live/dirtydata.ai/privkey.pem | SSL private key |
| `refresh_buffer_seconds` | int | No | 300 | Refresh before expiry |

### 4.7 Container Deployment Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    HOST MACHINE                          │
│                                                          │
│  Authorization Script (authorize_schwab_host.py)        │
│  ├─ Accesses SSL certs at /etc/letsencrypt             │
│  ├─ Starts HTTPS server on port 8443                   │
│  ├─ Receives OAuth callback                            │
│  └─ Writes tokens to project/.schwab_tokens.json       │
│                                                          │
│  Project Directory: /workspaces/options_income/         │
│  └─ .schwab_tokens.json ◄───────┐                      │
└──────────────────────────────────┼──────────────────────┘
                                   │ (workspace mount)
┌──────────────────────────────────┼──────────────────────┐
│                 DEVCONTAINER     │                       │
│                                  │                       │
│  Mounted: /workspaces/options_income/                   │
│  └─ .schwab_tokens.json ◄────────┘                      │
│                                                          │
│  Application (wheel_strategy_tool)                      │
│  ├─ Reads tokens from .schwab_tokens.json              │
│  ├─ Makes Schwab API calls                             │
│  ├─ Refreshes tokens when needed                       │
│  └─ Writes updated tokens back to .schwab_tokens.json  │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

**Execution Context Table**:

| Operation | Runs On | Access Requirements | Token File Access |
|-----------|---------|---------------------|-------------------|
| Initial Authorization | HOST | SSL certs, port 8443 | Write |
| Token Exchange | HOST | Network to Schwab API | Write |
| Application Startup | CONTAINER | Token file readable | Read |
| API Calls | CONTAINER | Network to Schwab API | Read |
| Token Refresh | CONTAINER | Network to Schwab API | Read/Write |
| Re-Authorization | HOST | SSL certs, port 8443 | Write (overwrite) |

---

## 5. User Stories

### US-O1: Initial Authorization

**As a** user setting up the system for the first time
**I want to** authorize the application to access my Schwab account
**So that** the system can retrieve my account data and market information

**Acceptance Criteria:**
- [ ] Running authorization script **on host** displays clear instructions
- [ ] Script clearly indicates it must run outside devcontainer
- [ ] Browser opens automatically to Schwab login page
- [ ] After logging in and granting access, browser shows success message
- [ ] Tokens are saved to project directory (`.schwab_tokens.json`)
- [ ] Subsequent API calls **from container** work without re-authorization
- [ ] Documentation clearly explains host vs container execution

### US-O2: Automatic Token Refresh

**As a** user with an existing authorization  
**I want** the system to automatically refresh my access token  
**So that** I don't have to manually re-authorize frequently

**Acceptance Criteria:**
- [ ] System detects when token is near expiry
- [ ] System automatically refreshes before expiry
- [ ] New tokens are saved to file
- [ ] API calls continue working without interruption
- [ ] No user interaction required

### US-O3: Token Status Check

**As a** user troubleshooting connection issues  
**I want to** check my current authorization status  
**So that** I can determine if re-authorization is needed

**Acceptance Criteria:**
- [ ] Can run command to see token status
- [ ] Status shows: authorized/not authorized
- [ ] Status shows: token expiration time
- [ ] Status shows: scope of access

### US-O4: Re-Authorization

**As a** user whose refresh token has expired  
**I want to** re-authorize the application  
**So that** I can continue using the system

**Acceptance Criteria:**
- [ ] System detects when refresh token is invalid
- [ ] System prompts user to re-authorize
- [ ] Re-authorization flow works same as initial
- [ ] Old tokens are replaced with new ones

### US-O5: Revoke Access

**As a** user who no longer wants the system to access my account  
**I want to** revoke the stored authorization  
**So that** the system can no longer access my data

**Acceptance Criteria:**
- [ ] Can run command to revoke access
- [ ] Local tokens are deleted
- [ ] Subsequent API calls fail with clear message
- [ ] Can re-authorize if desired later

---

## 6. Acceptance Criteria (Technical)

### 6.1 Authorization Flow

| # | Criterion | Verification |
|---|-----------|--------------|
| AC-O1 | Callback server starts on configured port with HTTPS | Integration test |
| AC-O2 | Authorization URL contains correct parameters | Unit test |
| AC-O3 | Callback correctly extracts authorization code | Unit test |
| AC-O4 | Token exchange returns valid tokens | Integration test (sandbox) |
| AC-O5 | Tokens are saved to configured file | Unit test |
| AC-O6 | Error responses are handled gracefully | Unit test |

### 6.2 Token Management

| # | Criterion | Verification |
|---|-----------|--------------|
| AC-O7 | Tokens load correctly from file | Unit test |
| AC-O8 | Token expiry is calculated correctly | Unit test |
| AC-O9 | Auto-refresh triggers before expiry | Unit test |
| AC-O10 | Refresh updates stored tokens | Unit test |
| AC-O11 | get_access_token returns valid token | Unit test |
| AC-O12 | Missing tokens raise clear exception | Unit test |

### 6.3 Error Handling

| # | Criterion | Verification |
|---|-----------|--------------|
| AC-O13 | Missing config raises ConfigurationError | Unit test |
| AC-O14 | Network errors trigger retry | Unit test |
| AC-O15 | Invalid refresh token raises clear error | Unit test |
| AC-O16 | Corrupted token file is handled | Unit test |

### 6.4 Integration

| # | Criterion | Verification |
|---|-----------|--------------|
| AC-O17 | Authorization header format is correct | Unit test |
| AC-O18 | Schwab API call succeeds with token | Integration test (sandbox) |
| AC-O19 | 401 response triggers appropriate error | Unit test |

### 6.5 Container Architecture

| # | Criterion | Verification |
|---|-----------|--------------|
| AC-O20 | Authorization script runs successfully on host | Manual test |
| AC-O21 | Token file written to project directory | Manual test |
| AC-O22 | Application in container reads tokens successfully | Integration test |
| AC-O23 | Token refresh from container writes back successfully | Integration test |
| AC-O24 | Same absolute path works in both contexts | Unit test |
| AC-O25 | .gitignore excludes token file | Manual verification |

---

## 7. Dependencies

### 7.1 External Dependencies

| Dependency | Version | Purpose |
|------------|---------|---------|
| `flask` | >= 2.0.0 | Callback server |
| `requests` | >= 2.31.0 | HTTP client for OAuth |

### 7.2 Infrastructure Dependencies

| Component | Requirement |
|-----------|-------------|
| Domain | `dirtydata.ai` with dyndns |
| SSL Certificate | Let's Encrypt for `dirtydata.ai` (accessible at `/etc/letsencrypt`) |
| Port Forwarding | Router forwards 8443 → host machine |
| Schwab App | Registered in Schwab Dev Portal |
| Devcontainer | VS Code devcontainer with workspace mount |
| SSL Mount | `/etc/letsencrypt` mounted read-only in devcontainer |

### 7.3 Schwab App Configuration

When creating the Schwab App in Dev Portal:

| Setting | Value |
|---------|-------|
| Callback URL | `https://dirtydata.ai:8443/oauth/callback` |
| App Type | Personal / Individual |
| Products | Market Data (minimum), optionally Trading |

---

## 8. Risks and Mitigations

### 8.1 Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| SSL certificate expires | Medium | High | Set up auto-renewal cron job |
| dyndns IP out of sync | Low | High | Monitor; most dyndns clients auto-update |
| Schwab API changes | Low | Medium | Version pin, monitor Schwab announcements |
| Port 8443 blocked by ISP | Low | High | Try alternate port; use ngrok as fallback |

### 8.2 Operational Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Refresh token expires (inactivity) | Medium | Low | Document re-auth process; make it easy |
| Token file permissions too open | Medium | Medium | Set permissions in code; warn user |
| User forgets to start auth server | High | Low | Clear instructions; auto-start if needed |

---

## 9. Implementation Phases

### Phase 1: Core OAuth (MVP)
- Configuration loading with container-compatible paths
- Token storage (file-based in project directory)
- Token manager (load, save, refresh check)
- Basic coordinator interface
- Path handling for host/container contexts

**Deliverable:** Can store/load tokens from shared location, check expiry

### Phase 2: Authorization Flow (Host Execution)
- Standalone callback server script for host execution
- HTTPS server with SSL certificate access
- Authorization URL generation
- Code exchange for tokens
- Browser integration
- Token file written to workspace directory

**Deliverable:** Complete initial authorization flow running on host

### Phase 3: Token Refresh (Container Execution)
- Token refresh from within container
- Automatic refresh before expiry
- Retry logic for network errors
- Error handling for invalid refresh tokens
- Write updated tokens back to shared file

**Deliverable:** Unattended token management from container

### Phase 4: Integration & Testing
- Integration with Schwab client module
- Split execution testing (host auth, container usage)
- Unit tests (>85% coverage)
- Integration tests with container architecture
- Container-specific documentation
- `.gitignore` configuration

**Deliverable:** Production-ready module with container support

---

## 10. Testing Requirements

### 10.1 Unit Tests

```
tests/oauth/
├── test_config.py           # Configuration tests
├── test_token_storage.py    # File storage tests
├── test_token_manager.py    # Token lifecycle tests
├── test_auth_server.py      # Callback server tests
└── test_coordinator.py      # Orchestration tests
```

### 10.2 Test Coverage Goals

| Module | Target |
|--------|--------|
| config.py | 100% |
| token_storage.py | 95% |
| token_manager.py | 90% |
| auth_server.py | 80% |
| coordinator.py | 85% |
| **Overall** | **> 85%** |

### 10.3 Integration Tests

- [ ] Full authorization flow with mock Schwab server
- [ ] Token refresh cycle simulation
- [ ] Error recovery scenarios

### 10.4 Manual Testing Checklist

- [ ] Fresh install: Authorization flow completes
- [ ] Restart: Tokens load from file
- [ ] After 25 minutes: Token auto-refreshes
- [ ] After 7+ days inactive: Re-auth required, works correctly
- [ ] Network disconnect during refresh: Retry succeeds
- [ ] Revoke: Tokens deleted, re-auth required

---

## 11. Documentation Requirements

### 11.1 Required Documentation

| Document | Purpose |
|----------|---------|
| README.md | Setup instructions, quick start |
| SETUP_INFRASTRUCTURE.md | HTTPS, port forwarding setup |
| TROUBLESHOOTING.md | Common errors and solutions |

### 11.2 Code Documentation

- All modules: Module-level docstring
- All classes: Class docstring with purpose
- All public functions: Full docstring with args, returns, raises
- Complex logic: Inline comments

---

## 12. Glossary

| Term | Definition |
|------|------------|
| **Access Token** | Short-lived token (~30 min) used for API authentication |
| **Refresh Token** | Long-lived token (~7 days) used to obtain new access tokens |
| **Authorization Code** | One-time code returned by Schwab after user grants access |
| **Callback URL** | URL where Schwab redirects after authorization |
| **CAG** | Consent and Grant - Schwab's term for the authorization step |
| **LMS** | Login Micro Site - Schwab's login page for OAuth |
| **Bearer Token** | Access token when used in Authorization header |
| **Grant Type** | OAuth term for the type of token request (authorization_code, refresh_token) |

---

## 13. Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-22 | Software Developer + Stock Quant | Initial requirements |

---

## 14. Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Product Owner | | | |
| Technical Lead | | | |
