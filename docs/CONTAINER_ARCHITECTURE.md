# Container Architecture for OAuth Integration

**Version:** 1.0
**Date:** January 25, 2026
**Purpose:** Document the split execution model for OAuth authorization in a devcontainer environment

---

## Overview

This application runs inside a devcontainer, but the OAuth authorization server must run on the host machine. This document explains the architecture, rationale, and workflows for this split execution model.

### Why Split Execution?

The OAuth callback server requires:
- Access to SSL certificates at `/etc/letsencrypt`
- Ability to bind to port 8443 on the host
- Direct network access for OAuth callbacks from Schwab

These requirements cannot be met from inside the devcontainer, necessitating a split execution model.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         HOST MACHINE                             │
│                                                                  │
│  ┌────────────────────────────────────────────────┐             │
│  │  scripts/authorize_schwab_host.py              │             │
│  │  - Runs OAuth callback server (HTTPS)          │             │
│  │  - Access to /etc/letsencrypt SSL certificates │             │
│  │  - Listens on port 8443                        │             │
│  │  - Receives authorization code from Schwab     │             │
│  │  - Exchanges code for access/refresh tokens    │             │
│  │  - Writes tokens to shared workspace file      │             │
│  └────────────────────────────────────────────────┘             │
│                         │                                        │
│                         ▼                                        │
│           /workspaces/options_income/.schwab_tokens.json         │
│                         │ (workspace mount - shared)             │
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
│  │  - Automatically refreshes expired tokens      │             │
│  │  - Writes refreshed tokens back to same file   │             │
│  │                                                 │             │
│  │  scripts/check_schwab_auth.py                  │             │
│  │  - Checks authorization status                 │             │
│  │  - Displays token expiration info              │             │
│  └────────────────────────────────────────────────┘             │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Token File Location

### Selected Approach: Project Directory

**Path:** `/workspaces/options_income/.schwab_tokens.json`

### Rationale

| Advantage | Description |
|-----------|-------------|
| **Same Path Everywhere** | Absolute path is identical in both host and container contexts |
| **No Additional Mounts** | Workspace is already mounted in devcontainer automatically |
| **Simple Configuration** | No context detection or path translation logic needed |
| **Shared Access** | Both host and container can read/write the same file |

### Security

- File permissions: `600` (user read/write only)
- Added to `.gitignore` to prevent accidental commits
- Contains sensitive credentials - never share or commit

---

## Execution Contexts

### What Runs Where

| Component | Context | Reason |
|-----------|---------|--------|
| `authorize_schwab_host.py` | **HOST** | Needs SSL certs, port 8443 |
| `check_schwab_auth.py` | **CONTAINER** | Safe status check only |
| `wheel_strategy_tool.py` | **CONTAINER** | Main application |
| OAuth Callback Server | **HOST** | HTTPS server for OAuth redirect |
| Token Refresh | **CONTAINER** | Automatic during API usage |

---

## First-Time Setup Workflow

### Step 1: Prerequisites (One-Time Setup)

On the **HOST machine**, ensure:

1. **Schwab Developer App Registered**
   - Visit https://developer.schwab.com
   - Register application
   - Set callback URL: `https://dirtydata.ai:8443/oauth/callback`
   - Note your `client_id` and `client_secret`

2. **SSL Certificates Installed**
   - Let's Encrypt certificates at `/etc/letsencrypt/live/dirtydata.ai/`
   - Certificates must be readable by the user running the script

3. **Port Forwarding Configured**
   - Router forwards port 8443 to host machine
   - Firewall allows inbound connections on port 8443

4. **Environment Variables Set**
   ```bash
   export SCHWAB_CLIENT_ID="your_client_id_from_schwab_portal"
   export SCHWAB_CLIENT_SECRET="your_client_secret_from_schwab_portal"
   ```

### Step 2: Run Authorization (HOST)

On the **HOST machine** (not in devcontainer):

```bash
# Navigate to project directory
cd /workspaces/options_income

# Run authorization script
python scripts/authorize_schwab_host.py
```

**What happens:**
1. Script verifies SSL certificates are accessible
2. Starts HTTPS server on port 8443
3. Opens browser to Schwab login page
4. You log in and authorize the application
5. Schwab redirects to callback server with authorization code
6. Script exchanges code for tokens
7. Tokens saved to `/workspaces/options_income/.schwab_tokens.json`
8. File permissions set to `600`

### Step 3: Verify Authorization (CONTAINER)

Inside the **devcontainer**:

```bash
# Check authorization status
python scripts/check_schwab_auth.py

# Verbose output
python scripts/check_schwab_auth.py --verbose
```

Expected output if successful:
```
======================================================================
SCHWAB OAUTH AUTHORIZATION STATUS
======================================================================

✅ AUTHORIZED

Status:      ✅ Active
Expires in:  28m

Application can now make API calls to Schwab.
======================================================================
```

### Step 4: Use Application (CONTAINER)

Inside the **devcontainer**, use the application normally:

```bash
# Run wheel strategy with Schwab data
wheel recommend NVDA --broker schwab

# The application will:
# - Load tokens from /workspaces/options_income/.schwab_tokens.json
# - Automatically refresh if expired
# - Make API calls with valid Bearer token
```

---

## Token Lifecycle

### Token Validity

| Token Type | Typical Lifetime | Notes |
|------------|------------------|-------|
| Access Token | 30 minutes | Used for API calls |
| Refresh Token | 7 days | Used to get new access tokens |

*Actual lifetimes may vary - check Schwab documentation*

### Automatic Refresh

The application automatically refreshes access tokens when:
- Token expires (after 30 minutes)
- Token expires soon (within 5 minutes of expiry)

**Refresh happens in the container** and updated tokens are written back to the same file.

### When Re-Authorization Needed

Re-authorize (run host script again) if:
- Refresh token expires (typically after 7 days of inactivity)
- User revokes access in Schwab account settings
- Token file is deleted or corrupted
- You want to authorize with a different Schwab account

---

## Common Workflows

### Daily Usage

**Already authorized? Just use the app in the container:**

```bash
# Inside devcontainer
wheel recommend TSLA --broker schwab
```

The application handles everything automatically.

### Check Authorization Status

```bash
# Inside devcontainer
python scripts/check_schwab_auth.py
```

### Re-Authorize

```bash
# Exit devcontainer, then on HOST:
python scripts/authorize_schwab_host.py --revoke
python scripts/authorize_schwab_host.py
```

### Switch to Different Account

```bash
# Exit devcontainer, then on HOST:
python scripts/authorize_schwab_host.py --revoke

# Log in with different account when browser opens
python scripts/authorize_schwab_host.py
```

---

## Troubleshooting

### Error: "Token file not found"

**Cause:** Authorization hasn't been run yet

**Solution:**
```bash
# Exit devcontainer
# On HOST machine:
python scripts/authorize_schwab_host.py
```

### Error: "SSL certificate not found"

**Cause:** SSL certificates not accessible on host

**Solution:**
1. Verify certificates exist:
   ```bash
   ls -la /etc/letsencrypt/live/dirtydata.ai/
   ```
2. Ensure your user has read permissions
3. Renew certificates if expired:
   ```bash
   sudo certbot renew
   ```

### Error: "Permission denied" writing tokens

**Cause:** File permissions issue

**Solution:**
```bash
# On host machine:
ls -la /workspaces/options_income/.schwab_tokens.json

# If permissions are wrong:
chmod 600 /workspaces/options_income/.schwab_tokens.json
```

### Error: "Port 8443 already in use"

**Cause:** Another process is using port 8443

**Solution:**
```bash
# Find process using port:
sudo lsof -i :8443

# Kill the process or use different port
# (update SCHWAB_CALLBACK_PORT environment variable)
```

### Token Refresh Fails in Container

**Cause:** Network connectivity or expired refresh token

**Solution:**
1. Check network connectivity:
   ```bash
   curl https://api.schwabapi.com
   ```
2. If refresh token expired, re-authorize:
   ```bash
   # Exit container, then on HOST:
   python scripts/authorize_schwab_host.py --revoke
   python scripts/authorize_schwab_host.py
   ```

### Browser Doesn't Open Automatically

**Cause:** No display/browser on host machine

**Solution:**
```bash
# Use --no-browser flag to display URL:
python scripts/authorize_schwab_host.py --no-browser

# Copy the displayed URL and paste in browser manually
```

---

## Devcontainer Configuration

### Required Configuration

File: `.devcontainer/devcontainer.json`

```json
{
  "mounts": [
    "source=/etc/letsencrypt,target=/etc/letsencrypt,type=bind,readonly"
  ]
}
```

**Note:** The workspace mount (`/workspaces/options_income`) is automatic - no additional configuration needed for the token file.

### .gitignore Entry

File: `.gitignore`

```
# OAuth Tokens (contains sensitive credentials)
.schwab_tokens.json
```

---

## Security Considerations

### Token Storage

| Aspect | Implementation | Risk Level |
|--------|----------------|------------|
| **Storage Format** | Plaintext JSON | Medium (acceptable for personal use) |
| **File Permissions** | 600 (user only) | Low |
| **Location** | Project directory (gitignored) | Low |
| **Network Transit** | HTTPS only | Low |

### Best Practices

1. **Never commit tokens** - Always check `.gitignore` includes `.schwab_tokens.json`
2. **Don't share token file** - Contains sensitive credentials
3. **Use separate credentials per environment** - Don't reuse production credentials for development
4. **Revoke when done** - Run `--revoke` if you won't use the application for extended periods
5. **Monitor access** - Check Schwab account settings periodically for authorized apps

### Future Enhancements

For production or multi-user deployments, consider:
- Encrypted token storage
- System keychain integration
- Secret management service (AWS Secrets Manager, HashiCorp Vault)
- Token encryption key derived from user password

---

## Quick Reference

### Host Machine Commands

```bash
# First-time authorization
python scripts/authorize_schwab_host.py

# Re-authorize (force new login)
python scripts/authorize_schwab_host.py --revoke
python scripts/authorize_schwab_host.py

# Revoke only
python scripts/authorize_schwab_host.py --revoke
```

### Container Commands

```bash
# Check authorization status
python scripts/check_schwab_auth.py

# Check with details
python scripts/check_schwab_auth.py --verbose

# Use application
wheel recommend AAPL --broker schwab
```

### File Locations

| File | Path | Context |
|------|------|---------|
| Authorization Script | `/workspaces/options_income/scripts/authorize_schwab_host.py` | HOST |
| Check Script | `/workspaces/options_income/scripts/check_schwab_auth.py` | CONTAINER |
| Token File | `/workspaces/options_income/.schwab_tokens.json` | BOTH (shared) |
| SSL Certificates | `/etc/letsencrypt/live/dirtydata.ai/` | HOST |

---

## FAQ

**Q: Can I run the authorization script inside the devcontainer?**
A: No. The script requires access to SSL certificates and port 8443, which are only available on the host.

**Q: What happens if I delete the token file?**
A: You'll need to re-authorize by running the host script again.

**Q: Can multiple containers share the same tokens?**
A: Yes, as long as they mount the same workspace directory.

**Q: How do I know if my tokens are expired?**
A: Run `python scripts/check_schwab_auth.py` in the container.

**Q: Do I need to re-authorize after restarting the container?**
A: No. Tokens persist in the workspace directory across container restarts.

**Q: What if I want to use a different Schwab account?**
A: Run `authorize_schwab_host.py --revoke` on the host, then authorize again. The browser will prompt for login.

---

**Last Updated:** 2026-01-25
**Maintained By:** Development Team
