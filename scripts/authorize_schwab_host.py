#!/usr/bin/env python3
"""
Schwab OAuth Authorization Script - MUST RUN ON HOST MACHINE

This script initiates the OAuth authorization flow with Schwab.
It MUST be run on the host machine (not inside the devcontainer) because it:
- Requires access to SSL certificates at /etc/letsencrypt
- Needs to bind to port 8443 for the OAuth callback
- Starts an HTTPS server to receive the authorization callback

After successful authorization, tokens are saved to:
    /workspaces/options_income/.schwab_tokens.json

The application running in the devcontainer will then be able to read
and refresh these tokens as needed.

Usage:
    # Run on HOST machine
    python scripts/authorize_schwab_host.py

    # To revoke existing authorization
    python scripts/authorize_schwab_host.py --revoke

Prerequisites:
    - Environment variables must be set:
        export SCHWAB_CLIENT_ID="your_client_id"
        export SCHWAB_CLIENT_SECRET="your_client_secret"
    - SSL certificates at /etc/letsencrypt/live/dirtydata.ai/
    - Port 8443 forwarded to this machine
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.oauth.coordinator import OAuthCoordinator
from src.oauth.exceptions import ConfigurationError

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def print_banner():
    """Print warning banner about host execution."""
    banner = """
╔═══════════════════════════════════════════════════════════════════════════╗
║                                                                           ║
║                   SCHWAB OAUTH AUTHORIZATION SCRIPT                       ║
║                                                                           ║
║  ⚠️  CRITICAL: THIS SCRIPT MUST RUN ON THE HOST MACHINE  ⚠️               ║
║                                                                           ║
║  This script requires:                                                    ║
║    • Access to SSL certificates at /etc/letsencrypt                       ║
║    • Ability to bind to port 8443                                         ║
║    • Browser access for Schwab login                                      ║
║                                                                           ║
║  DO NOT run this script inside the devcontainer!                          ║
║                                                                           ║
╚═══════════════════════════════════════════════════════════════════════════╝
"""
    print(banner)


def verify_ssl_certificates(coordinator: OAuthCoordinator) -> bool:
    """
    Verify SSL certificates are accessible.

    Args:
        coordinator: OAuth coordinator with config

    Returns:
        True if certificates exist, False otherwise
    """
    cert_path = Path(coordinator.config.ssl_cert_path)
    key_path = Path(coordinator.config.ssl_key_path)

    if not cert_path.exists():
        logger.error(f"❌ SSL certificate not found: {cert_path}")
        logger.error("   Ensure Let's Encrypt certificates are installed")
        logger.error("   and accessible at /etc/letsencrypt")
        return False

    if not key_path.exists():
        logger.error(f"❌ SSL key not found: {key_path}")
        logger.error("   Ensure Let's Encrypt certificates are installed")
        logger.error("   and accessible at /etc/letsencrypt")
        return False

    logger.info(f"✅ SSL certificate found: {cert_path}")
    logger.info(f"✅ SSL key found: {key_path}")
    return True


def set_token_file_permissions(token_file: Path) -> None:
    """
    Set secure permissions on token file (user read/write only).

    Args:
        token_file: Path to token file
    """
    try:
        # chmod 600 - user read/write only
        token_file.chmod(0o600)
        logger.info(f"✅ Set secure permissions (600) on {token_file}")
    except Exception as e:
        logger.warning(f"⚠️  Could not set file permissions: {e}")


def authorize(open_browser: bool = True) -> int:
    """
    Run the authorization flow.

    Args:
        open_browser: Whether to automatically open browser

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    try:
        # Create coordinator
        coordinator = OAuthCoordinator()

        # Verify SSL certificates
        if not verify_ssl_certificates(coordinator):
            return 1

        # Check if already authorized
        if coordinator.is_authorized():
            status = coordinator.get_status()
            expires_in = int(status['expires_in_seconds'])

            if expires_in <= 0:
                # Access token expired - warn about potential refresh token expiry
                logger.warning("⚠️  Access token has expired.")
                logger.warning("   If the token was last refreshed more than 7 days ago,")
                logger.warning("   the refresh token has also expired.")
                logger.warning("   Use --revoke to re-authorize if API calls fail.")
            else:
                logger.info("✅ Already authorized!")
                logger.info(f"   Token expires in {expires_in} seconds")

            logger.info("   Use --revoke to re-authorize")
            return 0

        # Run authorization flow
        logger.info("Starting OAuth authorization flow...")
        success = coordinator.run_authorization_flow(open_browser=open_browser)

        if success:
            # Set secure permissions on token file
            token_file = Path(coordinator.config.token_file)
            if token_file.exists():
                set_token_file_permissions(token_file)

            logger.info("✅ Authorization successful!")
            logger.info(f"   Tokens saved to: {coordinator.config.token_file}")
            logger.info("")
            logger.info("Next steps:")
            logger.info("1. Start (or restart) your devcontainer")
            logger.info("2. Run your application inside the devcontainer")
            logger.info("3. The application will automatically use these tokens")
            return 0
        else:
            logger.error("❌ Authorization failed")
            logger.error("   Please check the error messages above and try again")
            return 1

    except ConfigurationError as e:
        logger.error(f"❌ Configuration error: {e}")
        logger.error("")
        logger.error("Please ensure environment variables are set:")
        logger.error("  export SCHWAB_CLIENT_ID='your_client_id'")
        logger.error("  export SCHWAB_CLIENT_SECRET='your_client_secret'")
        return 1
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


def revoke() -> int:
    """
    Revoke current authorization.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    try:
        coordinator = OAuthCoordinator()

        if not coordinator.is_authorized():
            logger.info("No authorization found to revoke")
            return 0

        coordinator.revoke()
        logger.info("✅ Authorization revoked")
        logger.info(f"   Token file deleted: {coordinator.config.token_file}")
        logger.info("")
        logger.info("Run this script again to re-authorize")
        return 0

    except Exception as e:
        logger.error(f"❌ Error revoking authorization: {e}")
        return 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Schwab OAuth Authorization - MUST RUN ON HOST MACHINE",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Prerequisites:
  1. Set environment variables:
       export SCHWAB_CLIENT_ID='your_client_id'
       export SCHWAB_CLIENT_SECRET='your_client_secret'

  2. Ensure SSL certificates are installed at:
       /etc/letsencrypt/live/dirtydata.ai/

  3. Ensure port 8443 is forwarded to this machine

Examples:
  # Run authorization flow
  python scripts/authorize_schwab_host.py

  # Revoke existing authorization
  python scripts/authorize_schwab_host.py --revoke
        """,
    )
    parser.add_argument(
        "--revoke",
        action="store_true",
        help="Revoke existing authorization and delete tokens",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't automatically open browser (display URL only)",
    )

    args = parser.parse_args()

    # Print banner
    print_banner()

    # Handle revoke
    if args.revoke:
        return revoke()

    # Run authorization
    return authorize(open_browser=not args.no_browser)


if __name__ == "__main__":
    sys.exit(main())
