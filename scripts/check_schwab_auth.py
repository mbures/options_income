#!/usr/bin/env python3
"""
Schwab OAuth Authorization Status Checker - RUNS IN DEVCONTAINER

This script checks the current Schwab OAuth authorization status.
It reads tokens from the file written by the host authorization script
and displays information about the authorization state.

This script is safe to run inside the devcontainer.

Usage:
    # Inside devcontainer
    python scripts/check_schwab_auth.py

    # Verbose output with token details
    python scripts/check_schwab_auth.py --verbose
"""

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.oauth.coordinator import OAuthCoordinator
from src.oauth.exceptions import ConfigurationError

# Setup logging
logging.basicConfig(
    level=logging.WARNING,  # Quiet by default
    format="%(message)s",
)
logger = logging.getLogger(__name__)


def format_time_remaining(seconds: float) -> str:
    """
    Format seconds into human-readable time remaining.

    Args:
        seconds: Number of seconds

    Returns:
        Formatted string (e.g., "2h 15m", "45m", "expired")
    """
    if seconds <= 0:
        return "expired"

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)

    if hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        return f"{minutes}m"
    else:
        return f"{int(seconds)}s"


def check_authorization(verbose: bool = False) -> int:
    """
    Check and display authorization status.

    Args:
        verbose: Whether to show detailed information

    Returns:
        Exit code (0 if authorized, 1 if not authorized, 2 on error)
    """
    try:
        # Create coordinator (reads config from environment)
        coordinator = OAuthCoordinator()

        # Get token file path
        token_file = Path(coordinator.config.token_file)

        # Print header
        print("=" * 70)
        print("SCHWAB OAUTH AUTHORIZATION STATUS")
        print("=" * 70)
        print()

        # Check if token file exists
        if not token_file.exists():
            print("❌ NOT AUTHORIZED")
            print()
            print(f"Token file not found: {token_file}")
            print()
            print("To authorize:")
            print("  1. Exit the devcontainer")
            print("  2. On the HOST machine, run:")
            print("       python scripts/authorize_schwab_host.py")
            print("  3. Return to the devcontainer")
            print()
            return 1

        # Check authorization status
        status = coordinator.get_status()

        if not status.get("authorized", False):
            print("❌ NOT AUTHORIZED")
            print()
            print(f"Reason: {status.get('message', 'Unknown')}")
            print()
            print("To re-authorize:")
            print("  1. Exit the devcontainer")
            print("  2. On the HOST machine, run:")
            print("       python scripts/authorize_schwab_host.py --revoke")
            print("       python scripts/authorize_schwab_host.py")
            print("  3. Return to the devcontainer")
            print()
            return 1

        # Authorized!
        print("✅ AUTHORIZED")
        print()

        # Show token details
        expired = status.get("expired", False)
        expires_at = status.get("expires_at", "")
        expires_in_seconds = status.get("expires_in_seconds", 0)

        if expired:
            print(f"Status:      ⚠️  Token expired")
            print(f"Expired at:  {expires_at}")
            print()
            print("The token will be automatically refreshed on next API call.")
        else:
            time_remaining = format_time_remaining(expires_in_seconds)
            print(f"Status:      ✅ Active")
            print(f"Expires in:  {time_remaining}")
            if verbose:
                print(f"Expires at:  {expires_at}")

        if verbose:
            print(f"Scope:       {status.get('scope', 'N/A')}")
            print(f"Token file:  {token_file}")
            print()
            print("Token file info:")
            stat = token_file.stat()
            print(f"  Size:        {stat.st_size} bytes")
            print(f"  Permissions: {oct(stat.st_mode)[-3:]}")
            modified = datetime.fromtimestamp(stat.st_mtime)
            print(f"  Modified:    {modified.strftime('%Y-%m-%d %H:%M:%S')}")

        print()
        print("Application can now make API calls to Schwab.")
        print("=" * 70)
        print()

        return 0

    except ConfigurationError as e:
        print("❌ CONFIGURATION ERROR")
        print()
        print(f"Error: {e}")
        print()
        print("Ensure environment variables are set:")
        print("  SCHWAB_CLIENT_ID")
        print("  SCHWAB_CLIENT_SECRET")
        print()
        return 2
    except Exception as e:
        print("❌ ERROR")
        print()
        print(f"Unexpected error: {e}")
        print()
        if verbose:
            import traceback
            traceback.print_exc()
        return 2


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Check Schwab OAuth authorization status (runs in devcontainer)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed token information",
    )

    args = parser.parse_args()

    return check_authorization(verbose=args.verbose)


if __name__ == "__main__":
    sys.exit(main())
