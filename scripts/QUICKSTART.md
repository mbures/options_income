# Quick Start: Schwab OAuth Authorization

This is a condensed guide for setting up and running the Schwab OAuth authorization on your host machine.

## Prerequisites

Before you begin, ensure you have:

1. ✅ Schwab Developer credentials (Client ID and Secret) from [developer.schwab.com](https://developer.schwab.com)
2. ✅ SSL certificate (Let's Encrypt recommended)
3. ✅ Port forwarding configured (8443 → your host machine)
4. ✅ Domain pointing to your public IP

See [docs/SCHWAB_OAUTH_SETUP.md](../docs/SCHWAB_OAUTH_SETUP.md) for detailed setup if you haven't completed these steps.

## One-Time Setup

### 1. Create Virtual Environment

```bash
# From project root on HOST machine
cd /path/to/options_income

# Run automated setup
bash scripts/setup_host.sh
```

This creates `scripts/venv/` with minimal dependencies (flask, requests).

### 2. Set Environment Variables

```bash
# Add to ~/.bashrc or ~/.zshrc
export SCHWAB_CLIENT_ID="your_client_id_from_dev_portal"
export SCHWAB_CLIENT_SECRET="your_client_secret_from_dev_portal"

# Optional: customize if needed
export SCHWAB_CALLBACK_HOST="yourdomain.com"  # default: dirtydata.ai
export SCHWAB_CALLBACK_PORT="8443"            # default: 8443

# Reload shell configuration
source ~/.bashrc  # or source ~/.zshrc
```

## Run Authorization

Every time you need to authorize or re-authorize:

```bash
# 1. Navigate to project directory
cd /path/to/options_income

# 2. Activate virtual environment
source scripts/venv/bin/activate

# 3. Run authorization script
python scripts/authorize_schwab_host.py

# 4. Follow browser prompts to authorize

# 5. Deactivate venv when done
deactivate
```

## Expected Flow

1. Script starts HTTPS server on port 8443
2. Browser opens to Schwab authorization page
3. You sign in and approve access
4. Callback received, tokens exchanged
5. Tokens saved to `/workspaces/options_income/.schwab_tokens.json`
6. Done! Container can now use Schwab API

## Verify Success

```bash
# Check token file created with secure permissions
ls -lh /workspaces/options_income/.schwab_tokens.json
# Should show: -rw------- 1 user user 1.2K ...
```

## Use in Container

After authorization, open the devcontainer and use Schwab:

```bash
# Test from container
python -c "from src.oauth.coordinator import OAuthCoordinator; print(OAuthCoordinator().get_status())"

# Use with wheel CLI
python -m src.wheel.cli --broker schwab status
python -m src.wheel.cli --broker schwab recommend AAPL
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'flask'"

Forgot to activate venv:
```bash
source scripts/venv/bin/activate
```

### "Missing Schwab OAuth credentials"

Environment variables not set:
```bash
echo $SCHWAB_CLIENT_ID
echo $SCHWAB_CLIENT_SECRET
# If empty, export them and try again
```

### "SSL certificate not found"

Check certificate paths:
```bash
ls -l /etc/letsencrypt/live/yourdomain.com/fullchain.pem
ls -l /etc/letsencrypt/live/yourdomain.com/privkey.pem
```

### "Address already in use"

Port 8443 is busy:
```bash
sudo lsof -i :8443  # See what's using it
# Either kill that process or use different port:
export SCHWAB_CALLBACK_PORT="9443"
```

## Re-Authorization

Tokens expire after 7 days. To re-authorize:

```bash
source scripts/venv/bin/activate
python scripts/authorize_schwab_host.py
deactivate
```

Or to revoke and start fresh:

```bash
source scripts/venv/bin/activate
python scripts/authorize_schwab_host.py --revoke
python scripts/authorize_schwab_host.py
deactivate
```

## Documentation

- **Detailed Setup Guide**: [docs/SCHWAB_OAUTH_SETUP.md](../docs/SCHWAB_OAUTH_SETUP.md)
- **Scripts README**: [scripts/README.md](README.md)
- **Container Architecture**: [docs/CONTAINER_ARCHITECTURE.md](../docs/CONTAINER_ARCHITECTURE.md)
- **OAuth Design**: [docs/oauth_design.md](../docs/oauth_design.md)

## Need Help?

1. Check [Troubleshooting](#troubleshooting) above
2. See full troubleshooting guide in [docs/SCHWAB_OAUTH_SETUP.md](../docs/SCHWAB_OAUTH_SETUP.md)
3. Review [scripts/README.md](README.md)
4. Check OAuth logs in console output
