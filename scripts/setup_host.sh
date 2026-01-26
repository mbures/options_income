#!/bin/bash
# Setup script for host-side OAuth authorization
#
# This creates a lightweight virtual environment for running the Schwab
# OAuth authorization script on the HOST machine (outside devcontainer).
#
# Usage:
#   bash scripts/setup_host.sh
#
# After setup, activate the venv and run:
#   source scripts/venv/bin/activate
#   python scripts/authorize_schwab_host.py

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/venv"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"

echo "=== Schwab OAuth Host Setup ==="
echo ""
echo "This will create a Python virtual environment for running"
echo "the OAuth authorization script on your host machine."
echo ""

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 not found. Please install Python 3.8 or later."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "✓ Found Python $PYTHON_VERSION"

# Create virtual environment
if [ -d "$VENV_DIR" ]; then
    echo ""
    echo "Virtual environment already exists at: $VENV_DIR"
    read -p "Recreate it? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Removing existing venv..."
        rm -rf "$VENV_DIR"
    else
        echo "Using existing venv."
        exit 0
    fi
fi

echo ""
echo "Creating virtual environment..."
python3 -m venv "$VENV_DIR"

# Activate venv
echo "Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip > /dev/null

# Install dependencies
echo "Installing dependencies from scripts/requirements.txt..."
pip install -r "${SCRIPT_DIR}/requirements.txt"

echo ""
echo "=== Setup Complete! ==="
echo ""
echo "To use the OAuth authorization script:"
echo ""
echo "  1. Activate the virtual environment:"
echo "     source scripts/venv/bin/activate"
echo ""
echo "  2. Set your Schwab credentials (if not already set):"
echo "     export SCHWAB_CLIENT_ID=\"your_client_id\""
echo "     export SCHWAB_CLIENT_SECRET=\"your_client_secret\""
echo ""
echo "  3. Run the authorization script:"
echo "     python scripts/authorize_schwab_host.py"
echo ""
echo "  4. When done, deactivate the venv:"
echo "     deactivate"
echo ""
