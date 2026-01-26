# Scripts Folder

This folder contains host-side scripts that must be run **outside the devcontainer** on your host machine.

## OAuth Authorization Script

The `authorize_schwab_host.py` script runs the OAuth authorization flow and must execute on the host because:

- It runs an HTTPS callback server on port 8443
- The callback server must be accessible from the public internet
- Devcontainer networking doesn't support binding to host ports

## Setup (One-Time)

### Quick Setup

Run the automated setup script:

```bash
# From the project root directory
bash scripts/setup_host.sh
```

This will:
1. Create a Python virtual environment in `scripts/venv/`
2. Install minimal dependencies (flask, requests)
3. Display usage instructions

### Manual Setup

If you prefer manual setup:

```bash
# Navigate to scripts directory
cd scripts

# Create virtual environment
python3 -m venv venv

# Activate venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## SSL Certificate Setup (One-Time)

The OAuth callback server requires SSL certificates. Copy them to the project directory so the script can access them without sudo:

```bash
# From project root, create certificates directory
mkdir -p certs

# Copy SSL certificates (requires sudo once)
sudo cp /etc/letsencrypt/live/dirtydata.ai/fullchain.pem certs/
sudo cp /etc/letsencrypt/live/dirtydata.ai/privkey.pem certs/

# Make them readable by your user
sudo chown $USER:$USER certs/*.pem

# Set secure permissions (user read/write only)
chmod 600 certs/*.pem
```

**Note**: If your certificates renew, you'll need to copy them again.

## Usage

### 1. Set Schwab API Credentials

```bash
export SCHWAB_CLIENT_ID="your_client_id_from_schwab_dev_portal"
export SCHWAB_CLIENT_SECRET="your_client_secret_from_schwab_dev_portal"
```

**Tip**: Add these to your `~/.bashrc` or `~/.zshrc` to persist across sessions.

### 2. Run Authorization Helper Script

```bash
# From project root
./scripts/run_authorization.sh
```

The helper script automatically:
- Activates the virtual environment
- Sets correct paths for certificates and token file
- Validates that certificates exist
- Runs the authorization flow

The authorization flow will:
1. Start HTTPS callback server on port 8443
2. Open your browser to Schwab authorization page
3. Wait for you to authorize
4. Exchange authorization code for tokens
5. Save tokens to `.schwab_tokens.json`

### 3. Verify Token File Created

```bash
ls -lh .schwab_tokens.json
```

Should show a file with secure permissions (600).

### Alternative: Manual Method

If you prefer to run the authorization script directly:

```bash
# Activate virtual environment
source scripts/venv/bin/activate

# Set environment variables for certificate and token paths
export SCHWAB_TOKEN_FILE="$HOME/Projects/ai/options_income/.schwab_tokens.json"
export SCHWAB_SSL_CERT_PATH="$HOME/Projects/ai/options_income/certs/fullchain.pem"
export SCHWAB_SSL_KEY_PATH="$HOME/Projects/ai/options_income/certs/privkey.pem"

# Run authorization script
python scripts/authorize_schwab_host.py

# Deactivate when done
deactivate
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'flask'"

**Cause**: Virtual environment not activated or dependencies not installed.

**Solution**:
```bash
source scripts/venv/bin/activate
pip install -r scripts/requirements.txt
```

### "OSError: [Errno 98] Address already in use"

**Cause**: Port 8443 is already in use by another process.

**Solution**:
```bash
# Find what's using port 8443
sudo lsof -i :8443

# Kill the process or use a different port
export SCHWAB_CALLBACK_PORT="9443"
```

### "SSL certificate not found"

**Cause**: SSL certificate files not copied to `certs/` directory.

**Solution**: Copy certificates from Let's Encrypt:
```bash
mkdir -p certs
sudo cp /etc/letsencrypt/live/dirtydata.ai/fullchain.pem certs/
sudo cp /etc/letsencrypt/live/dirtydata.ai/privkey.pem certs/
sudo chown $USER:$USER certs/*.pem
chmod 600 certs/*.pem
```

For Let's Encrypt setup, see [docs/SCHWAB_OAUTH_SETUP.md](../docs/SCHWAB_OAUTH_SETUP.md).

### "Missing Schwab OAuth credentials"

**Cause**: Environment variables not set.

**Solution**:
```bash
export SCHWAB_CLIENT_ID="your_client_id"
export SCHWAB_CLIENT_SECRET="your_client_secret"
```

## Re-Authorization

To revoke and re-authorize (e.g., after credential changes):

```bash
# Revoke existing tokens
./scripts/run_authorization.sh --revoke

# Run new authorization
./scripts/run_authorization.sh
```

## Files

- **setup_host.sh**: Automated setup script (creates venv, installs deps)
- **requirements.txt**: Minimal dependencies for host scripts
- **run_authorization.sh**: Helper script that sets environment variables and runs authorization
- **authorize_schwab_host.py**: OAuth authorization script (called by run_authorization.sh)
- **venv/**: Virtual environment directory (created by setup, .gitignored)

## Security Notes

- **Never commit** `.schwab_tokens.json` to version control (already in .gitignore)
- **Keep credentials secure** - don't share your client secret
- **Use environment variables** for sensitive configuration
- **Virtual environment** isolates host dependencies from system Python

## Dependencies

Minimal dependencies installed in the virtual environment:

- **flask** (>=3.0.0): HTTPS callback server
- **requests** (>=2.31.0): HTTP requests for token exchange

The OAuth modules use only standard library beyond these two packages.

## Documentation

For complete setup instructions including SSL certificates, port forwarding, and architecture details, see:

- [Schwab OAuth Setup Guide](../docs/SCHWAB_OAUTH_SETUP.md)
- [Container Architecture](../docs/CONTAINER_ARCHITECTURE.md)
- [OAuth Design Document](../docs/oauth_design.md)

---

**Questions?** See the troubleshooting section in [docs/SCHWAB_OAUTH_SETUP.md](../docs/SCHWAB_OAUTH_SETUP.md)
