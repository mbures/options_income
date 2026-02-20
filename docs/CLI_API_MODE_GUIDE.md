# CLI API Mode Guide

This guide explains how to use the Wheel Strategy CLI in API mode, which allows the CLI to communicate with the backend API server instead of accessing the database directly.

## Overview

The CLI now supports two modes of operation:

1. **Direct Mode (Default)**: CLI accesses the database directly (legacy behavior)
2. **API Mode**: CLI communicates with the API server via HTTP

### Benefits of API Mode

- **Multi-user support**: Multiple clients can safely access the same data
- **Remote access**: CLI can connect to API server running on different machine
- **Portfolio management**: Organize wheels into portfolios
- **Better separation of concerns**: Database access centralized in API server
- **Scalability**: Easier to scale and deploy

## Configuration

### Configuration File

Create a configuration file at `~/.wheel_strategy/config.yaml`:

```yaml
# API Settings
api:
  url: "http://localhost:8000"
  timeout: 30
  use_api_mode: true  # Enable API mode by default

# Default Values
defaults:
  portfolio_id: null  # Set to a portfolio ID to use as default
  profile: "conservative"  # Default risk profile

# CLI Settings
cli:
  verbose: false
  json_output: false
```

### Environment Variables

You can also configure via environment variables (takes precedence over config file):

```bash
export WHEEL_API_URL="http://localhost:8000"
export WHEEL_API_TIMEOUT=30
export WHEEL_USE_API_MODE=1
export WHEEL_DEFAULT_PORTFOLIO_ID="<portfolio-id>"
export WHEEL_DEFAULT_PROFILE="moderate"
export WHEEL_VERBOSE=1
```

### Command-Line Options

Override configuration with command-line flags:

```bash
# Force API mode
wheel --api-mode list

# Force direct mode (bypass API)
wheel --direct-mode list

# Override API URL
wheel --api-url http://remote-server:8000 list

# Enable verbose output
wheel --verbose list

# Specify custom config file
wheel --config-file /path/to/config.yaml list
```

## Mode Selection Priority

The CLI determines which mode to use with this priority:

1. Command-line flags (`--api-mode` or `--direct-mode`)
2. Environment variables
3. Configuration file
4. Default (attempts API mode with fallback to direct mode)

## Starting the API Server

Before using API mode, start the API server:

```bash
# Start the API server
cd /workspaces/options_income
python -m uvicorn src.server.main:app --host 0.0.0.0 --port 8000
```

The server will be available at `http://localhost:8000`.

## Portfolio Management

Portfolios are only available in API mode.

### Create a Portfolio

```bash
# Create a portfolio
wheel portfolio create "Trading Portfolio" --capital 50000 --description "My main trading account"

# List portfolios
wheel portfolio list

# Show portfolio details
wheel portfolio show <portfolio-id>
```

### Set Default Portfolio

```bash
# Set as default (saved to config file)
wheel portfolio set-default <portfolio-id>
```

Now all commands will use this portfolio unless you specify `--portfolio`:

```bash
# Uses default portfolio
wheel init AAPL --capital 10000

# Use specific portfolio
wheel init MSFT --capital 15000 --portfolio <other-portfolio-id>
```

### Delete a Portfolio

```bash
# Delete portfolio (requires --confirm for safety)
wheel portfolio delete <portfolio-id> --confirm
```

**Warning**: This permanently deletes all wheels and trades in the portfolio!

## Working with Wheels

Most wheel commands work the same in both modes with automatic fallback.

### Initialize a Wheel

```bash
# In API mode (uses default portfolio)
wheel init AAPL --capital 10000 --profile moderate

# Specify portfolio
wheel init AAPL --capital 10000 --portfolio <portfolio-id>

# In direct mode (no portfolio concept)
wheel --direct-mode init AAPL --capital 10000
```

### List Wheels

```bash
# List wheels in default portfolio
wheel list

# List wheels in specific portfolio
wheel list --portfolio <portfolio-id>

# List wheels across all portfolios (API mode only)
wheel list --all-portfolios

# Force fresh data from market
wheel list --refresh
```

### View Status

```bash
# View specific wheel
wheel status AAPL --refresh

# View all wheels
wheel status --all

# Filter by portfolio
wheel status --all --portfolio <portfolio-id>
```

## Trading

Trade commands work the same in both modes:

```bash
# Record a trade
wheel record AAPL put --strike 145 --expiration 2026-03-20 --premium 2.50

# Record expiration
wheel expire AAPL --price 148.50

# Close trade early
wheel close AAPL --price 0.50

# Archive wheel (no open trades)
wheel archive AAPL
```

## Analysis

Analysis commands work in both modes with fallback:

```bash
# Get recommendation
wheel recommend AAPL

# Get all recommendations
wheel recommend --all

# View performance
wheel performance AAPL
wheel performance --all

# View trade history
wheel history AAPL

# Update settings
wheel update AAPL --profile aggressive

# Refresh snapshots (direct mode operation)
wheel refresh
```

## Fallback Behavior

If API mode is enabled but the server is unavailable, the CLI will:

1. Display a warning message (in verbose mode)
2. Automatically fall back to direct mode
3. Continue operation using direct database access

Example:

```bash
$ wheel --api-mode --verbose list
! API unavailable, using direct mode: Failed to connect to API server
Symbol   State                Strike  Current  DTE         Moneyness    Risk
================================================================================
AAPL     CASH                 ---     ---      ---         ---          ---
================================================================================
Total wheels: 1
```

This ensures the CLI continues to work even when the API server is down.

## Error Handling

### API Validation Errors

When the API returns validation errors (422), the CLI displays detailed messages:

```bash
$ wheel init AAPL
Error: Validation error: Must specify --capital and/or --shares
```

### Connection Errors

When the API is unavailable:

```bash
$ wheel --api-mode portfolio list
Error: API unavailable: Failed to connect to API server at http://localhost:8000
```

### Server Errors

When the API returns server errors (5xx):

```bash
$ wheel init AAPL --capital 10000
Error: Server error: Internal server error occurred
```

## Migration from Direct Mode

If you're currently using direct mode and want to migrate to API mode:

### Step 1: Start the API Server

```bash
python -m uvicorn src.server.main:app --host 0.0.0.0 --port 8000
```

### Step 2: Create Configuration File

```bash
mkdir -p ~/.wheel_strategy
cat > ~/.wheel_strategy/config.yaml <<EOF
api:
  url: "http://localhost:8000"
  use_api_mode: true
defaults:
  profile: "conservative"
cli:
  verbose: false
EOF
```

### Step 3: Create a Portfolio

```bash
wheel portfolio create "Main Portfolio" --capital 50000
wheel portfolio set-default <portfolio-id>
```

### Step 4: Import Existing Wheels (Optional)

Currently, there's no automated migration tool. You can:

1. Continue using direct mode for existing wheels
2. Manually recreate wheels in API mode
3. Use both modes side by side (they access the same database)

### Step 5: Use API Mode

```bash
# Now commands use API mode by default
wheel list
wheel init MSFT --capital 15000
```

## Troubleshooting

### API Server Not Starting

Check that port 8000 is not in use:

```bash
lsof -i :8000
```

### Connection Refused

Verify the API server is running:

```bash
curl http://localhost:8000/health
```

Should return: `{"status":"healthy"}`

### Wrong Portfolio

Check your default portfolio:

```bash
wheel portfolio list
```

The default portfolio is marked with an asterisk (*).

### Configuration Not Loading

Verify config file exists and is valid YAML:

```bash
cat ~/.wheel_strategy/config.yaml
python -c "import yaml; yaml.safe_load(open('$HOME/.wheel_strategy/config.yaml'))"
```

### Mixed Mode Issues

If you use both API mode and direct mode, they access the same database. This is safe but:

- Portfolio information is only visible in API mode
- Wheels created in direct mode won't be associated with a portfolio
- Use one mode consistently for best results

## Advanced Usage

### Remote API Server

Connect to API server running on another machine:

```bash
# Via command line
wheel --api-url http://192.168.1.100:8000 list

# Via environment variable
export WHEEL_API_URL="http://192.168.1.100:8000"
wheel list

# Via config file
cat > ~/.wheel_strategy/config.yaml <<EOF
api:
  url: "http://192.168.1.100:8000"
  use_api_mode: true
EOF
wheel list
```

### Custom Timeout

For slow networks or operations:

```bash
# Via command line (not currently supported, would need to add)
export WHEEL_API_TIMEOUT=60
wheel list
```

### JSON Output

Some commands support JSON output:

```bash
wheel --json performance AAPL > performance.json
```

### Automation

Use in scripts with error handling:

```bash
#!/bin/bash
set -e  # Exit on error

# Ensure API is available or fall back
if ! curl -s http://localhost:8000/health > /dev/null; then
    echo "Warning: API not available, using direct mode"
    MODE="--direct-mode"
else
    MODE="--api-mode"
fi

# Run commands
wheel $MODE list
wheel $MODE recommend --all
```

## API Endpoints Reference

For reference, the CLI uses these API endpoints:

- `GET /health` - Health check
- `GET /api/v1/portfolios/` - List portfolios
- `POST /api/v1/portfolios/` - Create portfolio
- `GET /api/v1/portfolios/{id}` - Get portfolio
- `GET /api/v1/portfolios/{id}/summary` - Get portfolio summary
- `DELETE /api/v1/portfolios/{id}` - Delete portfolio
- `GET /api/v1/portfolios/{id}/wheels` - List wheels in portfolio
- `POST /api/v1/portfolios/{id}/wheels` - Create wheel
- `GET /api/v1/wheels/{id}` - Get wheel
- `PUT /api/v1/wheels/{id}` - Update wheel
- `DELETE /api/v1/wheels/{id}` - Delete wheel
- `GET /api/v1/wheels/{id}/recommend` - Get recommendation
- `GET /api/v1/wheels/{id}/position` - Get position status
- `POST /api/v1/wheels/{id}/trades` - Record trade
- `GET /api/v1/wheels/{id}/trades` - List trades
- `POST /api/v1/trades/{id}/expire` - Expire trade
- `POST /api/v1/trades/{id}/close` - Close trade

## Next Steps

- Review [QUICKSTART.md](QUICKSTART.md) for basic CLI usage
- See [WHEEL_MONITORING_GUIDE.md](WHEEL_MONITORING_GUIDE.md) for monitoring features
- Check [prd_backend_server.md](prd_backend_server.md) for API server details
