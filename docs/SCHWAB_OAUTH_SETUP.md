# Schwab OAuth Setup Guide

This guide walks you through setting up OAuth 2.0 authentication with Charles Schwab's APIs to enable live market data and account access in the Options Income system.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Step 1: Schwab Developer Portal Setup](#step-1-schwab-developer-portal-setup)
- [Step 2: SSL Certificate Setup](#step-2-ssl-certificate-setup)
- [Step 3: Port Forwarding Configuration](#step-3-port-forwarding-configuration)
- [Step 4: Environment Configuration](#step-4-environment-configuration)
- [Step 5: Initial Authorization](#step-5-initial-authorization)
- [Step 6: Using Schwab in Container](#step-6-using-schwab-in-container)
- [Token Refresh](#token-refresh)
- [Troubleshooting](#troubleshooting)
- [Common Errors](#common-errors)

---

## Overview

The Options Income system integrates with Schwab APIs using OAuth 2.0 for secure authentication. The integration supports:

- **Real-time market data** (quotes, options chains)
- **Account data** (positions, balances)
- **Automated token refresh** (no re-authorization needed for 7 days)
- **Container-safe architecture** (tokens stored in project directory)

### Split Execution Model

Due to devcontainer networking limitations, the OAuth flow uses a **split execution model**:

```
┌─────────────────────────────────────────────────────────────┐
│                         HOST MACHINE                         │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Authorization Script (authorize_schwab_host.py)     │  │
│  │                                                        │  │
│  │  • Runs HTTPS callback server on port 8443           │  │
│  │  • Opens browser for user authorization              │  │
│  │  • Exchanges code for tokens                         │  │
│  │  • Writes tokens to project directory                │  │
│  └──────────────────────────────────────────────────────┘  │
│                           │                                  │
│                           ▼                                  │
│         /workspaces/options_income/.schwab_tokens.json      │
│                           │                                  │
└───────────────────────────┼──────────────────────────────────┘
                            │ (shared volume mount)
┌───────────────────────────┼──────────────────────────────────┐
│                           ▼                                  │
│                   DEVCONTAINER                               │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Application (wheel CLI, etc.)                       │  │
│  │                                                        │  │
│  │  • Reads tokens from project directory               │  │
│  │  • Auto-refreshes tokens when needed                 │  │
│  │  • Writes refreshed tokens back to same file         │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Why this approach?**
- Devcontainer cannot bind to host ports (callback server would be unreachable)
- Host can run HTTPS server and receive Schwab redirects
- Token file in project directory is accessible to both host and container
- Container can refresh tokens automatically without host involvement

---

## Architecture

See [CONTAINER_ARCHITECTURE.md](CONTAINER_ARCHITECTURE.md) for detailed architectural information.

### Key Components

- **OAuth Coordinator** (`src/oauth/coordinator.py`): High-level OAuth workflow orchestration
- **Token Manager** (`src/oauth/token_manager.py`): Token exchange, refresh, and validation
- **Token Storage** (`src/oauth/token_storage.py`): Secure token file management
- **Authorization Server** (`src/oauth/auth_server.py`): HTTPS callback server (HOST only)
- **Schwab Client** (`src/schwab/client.py`): Authenticated API client with auto-refresh

---

## Prerequisites

### Required

- **Schwab brokerage account** (for API access)
- **Domain name** with public DNS (e.g., dirtydata.ai)
- **SSL certificate** from a trusted CA (Let's Encrypt recommended)
- **Port forwarding** from public internet to host machine (port 8443)
- **Host machine access** (cannot run authorization from within container)

### Recommended

- **Let's Encrypt** with automatic certificate renewal
- **Static public IP** or dynamic DNS
- **Firewall rules** allowing inbound HTTPS (port 8443)

---

## Step 1: Schwab Developer Portal Setup

### 1.1 Create Schwab Developer Account

1. Go to [https://developer.schwab.com](https://developer.schwab.com)
2. Sign in with your Schwab brokerage credentials
3. Accept the Developer Portal Terms of Service

### 1.2 Register Your Application

1. Navigate to **"Apps"** → **"Create New App"**
2. Fill in application details:
   - **App Name**: Options Income System
   - **Description**: Automated options trading and analysis
   - **App Type**: Individual/Personal Use

3. **Configure OAuth Redirect URI**:
   ```
   https://yourdomain.com:8443/oauth/callback
   ```

   ⚠️ **Important**: Replace `yourdomain.com` with your actual domain (e.g., `dirtydata.ai`)

   ⚠️ **Must use HTTPS** - HTTP not supported

   ⚠️ **Port must match** your callback server configuration

4. Submit and wait for approval (typically instant for individual apps)

### 1.3 Save Credentials

After approval, save these values securely:

- **Client ID** (also called App Key) - format: `XXXXXXXXXXXXXXXXXXXXXXXXXXXX`
- **Client Secret** (also called App Secret) - keep this SECRET!

You'll need these for environment configuration.

---

## Step 2: SSL Certificate Setup

Schwab requires HTTPS for OAuth callbacks. You need a valid SSL certificate from a trusted Certificate Authority (CA).

### Option A: Let's Encrypt (Recommended)

Let's Encrypt provides free, automated SSL certificates that are automatically trusted by browsers.

#### Install Certbot

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install certbot

# macOS
brew install certbot
```

#### Obtain Certificate

```bash
# Using standalone mode (stops any web server temporarily)
sudo certbot certonly --standalone -d yourdomain.com

# Certificate files will be created at:
# /etc/letsencrypt/live/yourdomain.com/fullchain.pem  (certificate)
# /etc/letsencrypt/live/yourdomain.com/privkey.pem    (private key)
```

#### Set Up Auto-Renewal

```bash
# Test renewal
sudo certbot renew --dry-run

# Add renewal to cron (runs twice daily)
echo "0 */12 * * * root certbot renew --quiet" | sudo tee -a /etc/crontab
```

### Option B: Commercial Certificate

If you prefer a commercial certificate provider (DigiCert, Comodo, etc.):

1. Purchase certificate for your domain
2. Complete domain validation
3. Download certificate files
4. Note the paths to `fullchain.pem` and `privkey.pem`

### Verify Certificate

```bash
# Check certificate expiration
openssl x509 -in /etc/letsencrypt/live/yourdomain.com/fullchain.pem -noout -dates

# Test HTTPS server (optional)
python3 -m http.server --bind localhost 8443 \
  --certfile /etc/letsencrypt/live/yourdomain.com/fullchain.pem \
  --keyfile /etc/letsencrypt/live/yourdomain.com/privkey.pem
```

---

## Step 3: Port Forwarding Configuration

Your router must forward incoming HTTPS traffic (port 8443) from the public internet to your host machine.

### 3.1 Find Your Host Machine IP

```bash
# Linux/macOS
hostname -I | awk '{print $1}'

# Or
ip addr show | grep "inet " | grep -v 127.0.0.1
```

Note your local IP address (e.g., `192.168.1.100`)

### 3.2 Configure Router

Router configurations vary, but general steps:

1. Log into your router admin panel (typically http://192.168.1.1)
2. Find **Port Forwarding** or **NAT** settings
3. Add new port forwarding rule:
   - **External Port**: 8443
   - **Internal Port**: 8443
   - **Internal IP**: Your host machine IP (e.g., 192.168.1.100)
   - **Protocol**: TCP
   - **Name**: Schwab OAuth Callback

4. Save and apply changes

### 3.3 Verify Port Forwarding

From an external network (mobile phone on cellular, not WiFi):

```bash
# Replace yourdomain.com with your actual domain
curl -I https://yourdomain.com:8443

# Should eventually show "connection refused" or timeout
# (server not running yet, but port is open)
```

If you get "connection timed out" immediately, port forwarding may not be working.

### 3.4 Firewall Rules

Ensure firewall allows inbound connections on port 8443:

```bash
# Ubuntu/Debian (ufw)
sudo ufw allow 8443/tcp
sudo ufw reload

# CentOS/RHEL (firewalld)
sudo firewall-cmd --permanent --add-port=8443/tcp
sudo firewall-cmd --reload

# macOS
# System Preferences → Security & Privacy → Firewall → Firewall Options
# Add Python to allowed applications
```

---

## Step 4: Environment Configuration

### 4.1 Set Environment Variables

Add Schwab credentials to your environment:

```bash
# Edit your shell configuration file
nano ~/.bashrc   # or ~/.zshrc for zsh

# Add these lines at the end:
export SCHWAB_CLIENT_ID="your_client_id_here"
export SCHWAB_CLIENT_SECRET="your_client_secret_here"

# Optional: customize callback domain/port
export SCHWAB_CALLBACK_HOST="yourdomain.com"  # default: dirtydata.ai
export SCHWAB_CALLBACK_PORT="8443"            # default: 8443

# Optional: customize token file location
export SCHWAB_TOKEN_FILE="/workspaces/options_income/.schwab_tokens.json"

# Reload configuration
source ~/.bashrc
```

⚠️ **Security Note**: Keep your client secret secure. Never commit it to version control.

### 4.2 Verify Configuration

```bash
# Check environment variables are set
echo $SCHWAB_CLIENT_ID
echo $SCHWAB_CLIENT_SECRET
```

Both should print your credentials (not empty).

---

## Step 5: Initial Authorization

Initial authorization **MUST be run on the HOST machine** (not in the container).

### 5.1 Run Authorization Script on HOST

```bash
# Navigate to project directory on HOST (not in container)
cd /workspaces/options_income

# Run authorization script
python scripts/authorize_schwab_host.py
```

### 5.2 Authorization Flow

```
Starting Schwab OAuth authorization...

✓ Configuration loaded
✓ HTTPS callback server started on https://yourdomain.com:8443
✓ Opening browser for authorization...

----------------------------------------------------------------------
Authorize in browser: https://api.schwabapi.com/v1/oauth/authorize?...
----------------------------------------------------------------------

Waiting for authorization callback...
```

### 5.3 Complete Browser Authorization

1. **Browser opens automatically** to Schwab login page
2. **Sign in** with your Schwab brokerage credentials
3. **Review permissions** requested by your app
4. **Click "Allow"** to authorize
5. Browser redirects to `https://yourdomain.com:8443/oauth/callback?code=...`
6. Callback server receives the authorization code

### 5.4 Token Exchange

After receiving the callback:

```
✓ Authorization code received
✓ Exchanging code for tokens...
✓ Tokens saved to /workspaces/options_income/.schwab_tokens.json

Authorization complete!

Access token valid until: 2026-01-25 21:15:43
Refresh token valid until: 2026-02-01 20:15:43

You can now use the Schwab API from your devcontainer.
```

### 5.5 Verify Token File

```bash
# Check token file exists
ls -lh /workspaces/options_income/.schwab_tokens.json

# Should show file with secure permissions (600)
-rw------- 1 user user 1.2K Jan 25 20:15 .schwab_tokens.json
```

⚠️ **DO NOT** open or edit this file manually. It's managed automatically.

---

## Step 6: Using Schwab in Container

After initial authorization, you can use Schwab APIs from within the devcontainer.

### 6.1 Start Devcontainer

```bash
# Open VS Code
code .

# Reopen in Container (Ctrl+Shift+P → "Reopen in Container")
```

### 6.2 Verify Token Access from Container

```bash
# Inside container
python -c "from src.oauth.coordinator import OAuthCoordinator; c = OAuthCoordinator(); print(c.get_status())"
```

Expected output:
```
{'authorized': True, 'access_token_expires': '2026-01-25T21:15:43+00:00', 'refresh_token_expires': '2026-02-01T20:15:43+00:00'}
```

### 6.3 Use Schwab API

```python
from src.schwab.client import SchwabClient

# Client automatically uses OAuthCoordinator
client = SchwabClient()

# Get real-time quote
quote = client.get_quote("AAPL")
print(f"AAPL last price: ${quote['lastPrice']}")

# Get options chain
chain = client.get_option_chain("AAPL", strike_count=10)
print(f"Found {len(chain.contracts)} contracts")
```

### 6.4 Use Wheel CLI with Schwab

```bash
# Use Schwab as data source
python -m src.wheel.cli --broker schwab status

# Create wheel position using Schwab data
python -m src.wheel.cli --broker schwab create AAPL --capital 10000

# Get recommendation (uses Schwab for market data)
python -m src.wheel.cli --broker schwab recommend AAPL
```

---

## Token Refresh

Tokens are automatically refreshed by the application. No manual intervention needed.

### Refresh Behavior

- **Access tokens** expire after 30 minutes
- **Refresh tokens** expire after 7 days
- **Auto-refresh** happens 5 minutes before expiry (configurable)
- **Refreshed tokens** are written back to `/workspaces/options_income/.schwab_tokens.json`
- **Both host and container** can refresh tokens

### Monitoring Token Status

```bash
# Check token status from container
python -c "from src.oauth.coordinator import OAuthCoordinator; import json; c = OAuthCoordinator(); print(json.dumps(c.get_status(), indent=2))"
```

Output:
```json
{
  "authorized": true,
  "access_token_expires": "2026-01-25T21:45:43+00:00",
  "refresh_token_expires": "2026-02-01T20:15:43+00:00"
}
```

### Re-Authorization After Expiry

If refresh token expires (after 7 days), re-run authorization **on HOST**:

```bash
# On HOST (not container)
cd /workspaces/options_income
python scripts/authorize_schwab_host.py
```

---

## Troubleshooting

### Problem: "Missing Schwab OAuth credentials"

**Cause**: Environment variables not set

**Solution**:
```bash
# Verify environment variables on HOST
echo $SCHWAB_CLIENT_ID
echo $SCHWAB_CLIENT_SECRET

# If empty, set them and reload shell
export SCHWAB_CLIENT_ID="your_id"
export SCHWAB_CLIENT_SECRET="your_secret"
```

---

### Problem: "SSL certificate not found"

**Cause**: Certificate paths incorrect or certificates not installed

**Solution**:
```bash
# Check default paths exist
ls -l /etc/letsencrypt/live/yourdomain.com/fullchain.pem
ls -l /etc/letsencrypt/live/yourdomain.com/privkey.pem

# If using custom paths, set environment variables
export SCHWAB_SSL_CERT="/path/to/your/cert.pem"
export SCHWAB_SSL_KEY="/path/to/your/key.pem"
```

---

### Problem: "Connection timeout" during authorization

**Cause**: Port forwarding not configured or callback domain unreachable

**Solution**:
1. Verify domain resolves to your public IP:
   ```bash
   dig yourdomain.com +short
   # Should show your public IP
   ```

2. Test port forwarding from external network:
   ```bash
   # From phone on cellular (not WiFi)
   curl -I https://yourdomain.com:8443
   ```

3. Check router port forwarding rules (Step 3.2)

---

### Problem: "Callback server failed to start"

**Cause**: Port 8443 already in use or permission denied

**Solution**:
```bash
# Check what's using port 8443
sudo lsof -i :8443

# If something else is using it, stop that service or change port
export SCHWAB_CALLBACK_PORT="9443"  # Use different port

# Update Schwab Dev Portal callback URL to match new port
```

---

### Problem: "Token file not found" in container

**Cause**: Token file not in project directory or devcontainer volume mount incorrect

**Solution**:
1. Verify token file exists on host:
   ```bash
   # On HOST
   ls -l /workspaces/options_income/.schwab_tokens.json
   ```

2. Check devcontainer.json mounts project directory:
   ```json
   {
     "mounts": [
       "source=${localWorkspaceFolder},target=/workspaces/options_income,type=bind,consistency=cached"
     ]
   }
   ```

3. Rebuild container if needed:
   ```bash
   # In VS Code: Ctrl+Shift+P → "Rebuild Container"
   ```

---

### Problem: "401 Authentication failed" when using API

**Cause**: Tokens expired or invalid

**Solution**:
```bash
# Check token status
python -c "from src.oauth.coordinator import OAuthCoordinator; print(OAuthCoordinator().get_status())"

# If tokens expired, re-authorize on HOST
# (On HOST, not container)
python scripts/authorize_schwab_host.py
```

---

### Problem: "Browser doesn't open automatically"

**Cause**: No default browser configured or running headless

**Solution**:
```bash
# Manual authorization URL is printed to console
# Copy the URL and paste into browser manually

Starting Schwab OAuth authorization...
----------------------------------------------------------------------
Authorize in browser: https://api.schwabapi.com/v1/oauth/authorize?...
----------------------------------------------------------------------

# Copy this URL and open in browser
```

---

## Common Errors

### `ConfigurationError: Missing Schwab OAuth credentials`

- Environment variables `SCHWAB_CLIENT_ID` and `SCHWAB_CLIENT_SECRET` not set
- See Step 4.1 for configuration

### `AuthorizationError: SSL certificate not found`

- SSL certificate files not found at expected paths
- See Step 2 for SSL setup

### `TokenNotAvailableError: No valid OAuth tokens available`

- Authorization not completed or tokens expired
- Run `scripts/authorize_schwab_host.py` on HOST

### `SchwabAuthenticationError: Authentication failed (401)`

- Access token expired and refresh failed
- Check token status and re-authorize if needed

### `ConfigurationError: callback_port must be between 1 and 65535`

- Invalid port configuration
- Ensure `SCHWAB_CALLBACK_PORT` is a valid port number (default: 8443)

---

## Security Best Practices

### Token File Security

- **Never commit** `.schwab_tokens.json` to version control (added to `.gitignore`)
- **File permissions** automatically set to 600 (owner read/write only)
- **Secure storage** - tokens stored encrypted at rest by filesystem

### Credential Management

- **Client secret** should never be shared or committed to version control
- **Use environment variables** for configuration (not hardcoded)
- **Rotate credentials** periodically via Schwab Developer Portal

### Network Security

- **HTTPS only** - never use HTTP for OAuth callbacks
- **Valid SSL certificate** - use trusted CA (Let's Encrypt recommended)
- **Firewall rules** - only allow necessary inbound connections

---

## Advanced Configuration

### Custom Token File Location

```bash
# Set custom token file path
export SCHWAB_TOKEN_FILE="/custom/path/tokens.json"

# Ensure path is accessible to both host and container
```

### Custom Callback Configuration

```bash
# Use different callback domain
export SCHWAB_CALLBACK_HOST="custom.example.com"
export SCHWAB_CALLBACK_PORT="9443"

# Remember to update Schwab Dev Portal redirect URI to match
```

### Custom Refresh Buffer

```bash
# Refresh tokens 10 minutes before expiry (default: 5 minutes)
export SCHWAB_REFRESH_BUFFER_SECONDS="600"
```

---

## References

- [Schwab Developer Portal](https://developer.schwab.com)
- [Schwab API Documentation](https://developer.schwab.com/products/trader-api--individual/details/specifications/Market-Data-Production)
- [OAuth 2.0 Specification](https://oauth.net/2/)
- [Let's Encrypt Documentation](https://letsencrypt.org/docs/)
- [Container Architecture Guide](CONTAINER_ARCHITECTURE.md)
- [OAuth Design Document](oauth_design.md)
- [OAuth Requirements](oauth_requirements.md)

---

## Support

For issues and questions:

1. Check the [Troubleshooting](#troubleshooting) section above
2. Review [Common Errors](#common-errors)
3. Consult the [Container Architecture Guide](CONTAINER_ARCHITECTURE.md)
4. Open an issue in the project repository

---

**Last Updated**: January 25, 2026
