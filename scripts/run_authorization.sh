#!/bin/bash
#
# OAuth Authorization Helper Script
#
# This script sets up the correct environment variables and runs
# the Schwab OAuth authorization on the host machine.
#

# Get the project root directory (parent of scripts/)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Set environment variables for host machine paths
export SCHWAB_TOKEN_FILE="${PROJECT_ROOT}/.schwab_tokens.json"
export SCHWAB_SSL_CERT_PATH="${PROJECT_ROOT}/certs/fullchain.pem"
export SCHWAB_SSL_KEY_PATH="${PROJECT_ROOT}/certs/privkey.pem"

# Display configuration
echo "Using configuration:"
echo "  Token file: ${SCHWAB_TOKEN_FILE}"
echo "  SSL cert:   ${SCHWAB_SSL_CERT_PATH}"
echo "  SSL key:    ${SCHWAB_SSL_KEY_PATH}"
echo ""

# Check if certificates exist
if [[ ! -f "${SCHWAB_SSL_CERT_PATH}" ]]; then
    echo "❌ Error: SSL certificate not found at ${SCHWAB_SSL_CERT_PATH}"
    echo ""
    echo "Please copy certificates to ${PROJECT_ROOT}/certs/:"
    echo "  sudo cp /etc/letsencrypt/live/dirtydata.ai/fullchain.pem ${PROJECT_ROOT}/certs/"
    echo "  sudo cp /etc/letsencrypt/live/dirtydata.ai/privkey.pem ${PROJECT_ROOT}/certs/"
    echo "  sudo chown \$USER:\$USER ${PROJECT_ROOT}/certs/*.pem"
    echo "  chmod 600 ${PROJECT_ROOT}/certs/*.pem"
    exit 1
fi

if [[ ! -f "${SCHWAB_SSL_KEY_PATH}" ]]; then
    echo "❌ Error: SSL key not found at ${SCHWAB_SSL_KEY_PATH}"
    exit 1
fi

# Check if required environment variables are set
if [[ -z "${SCHWAB_CLIENT_ID}" ]] || [[ -z "${SCHWAB_CLIENT_SECRET}" ]]; then
    echo "❌ Error: Schwab credentials not set"
    echo ""
    echo "Please set environment variables:"
    echo "  export SCHWAB_CLIENT_ID='your_client_id'"
    echo "  export SCHWAB_CLIENT_SECRET='your_client_secret'"
    exit 1
fi

# Run the authorization script
python "${PROJECT_ROOT}/scripts/authorize_schwab_host.py" "$@"
