"""
OAuth callback server for Schwab API integration.

This module provides an HTTPS server that handles OAuth callbacks during
the authorization flow. The server MUST run on the HOST machine (not in
devcontainer) to access SSL certificates and port 8443.

IMPORTANT: This server is designed for single-user, personal use. It runs
temporarily during the authorization flow and shuts down after receiving
the callback.
"""

import logging
import ssl
import threading
import time
import webbrowser
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

from flask import Flask, request, Response

from .config import SchwabOAuthConfig

logger = logging.getLogger(__name__)


@dataclass
class AuthorizationResult:
    """
    Result of OAuth authorization flow.

    Attributes:
        success: Whether authorization succeeded
        authorization_code: Authorization code from callback (if successful)
        error: Error code from OAuth provider (if failed)
        error_description: Human-readable error description (if failed)
    """

    success: bool
    authorization_code: Optional[str] = None
    error: Optional[str] = None
    error_description: Optional[str] = None


class OAuthCallbackServer:
    """
    Local HTTPS server to handle OAuth callback.

    This server runs temporarily during the OAuth flow to receive
    the authorization code from Schwab's redirect. It MUST run on
    the HOST machine (outside devcontainer) to access SSL certificates
    and bind to port 8443.

    The server:
    1. Starts HTTPS listener on configured port
    2. Generates authorization URL
    3. Opens browser (or displays URL)
    4. Waits for OAuth callback
    5. Shuts down after receiving callback

    Security:
    - Uses SSL/TLS (required by Schwab)
    - Binds to 0.0.0.0 (accessible from router for OAuth redirect)
    - Single-use (shuts down after one callback)
    - No persistent state
    """

    def __init__(self, config: SchwabOAuthConfig):
        """
        Initialize callback server.

        Args:
            config: OAuth configuration with SSL cert paths
        """
        self.config = config
        self.app = Flask(__name__)
        self.app.logger.setLevel(logging.WARNING)  # Suppress Flask logs
        self.server: Optional[threading.Thread] = None
        self.result: Optional[AuthorizationResult] = None
        self._shutdown_event = threading.Event()
        self._server_ready = threading.Event()

        # Register routes
        self.app.add_url_rule(
            self.config.callback_path,
            "oauth_callback",
            self._handle_callback,
            methods=["GET"],
        )

        self.app.add_url_rule(
            "/oauth/status", "oauth_status", self._handle_status, methods=["GET"]
        )

    def _handle_callback(self) -> Response:
        """Handle OAuth callback from Schwab."""
        logger.info("Received OAuth callback")

        # Check for error response
        error = request.args.get("error")
        if error:
            error_desc = request.args.get("error_description", "Unknown error")
            logger.error(f"OAuth error: {error} - {error_desc}")
            self.result = AuthorizationResult(
                success=False, error=error, error_description=error_desc
            )
            self._shutdown_event.set()
            return Response(
                f"""<html>
                <head><title>Authorization Failed</title></head>
                <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px;">
                    <h1 style="color: #d32f2f;">❌ Authorization Failed</h1>
                    <p><strong>Error:</strong> {error}</p>
                    <p><strong>Description:</strong> {error_desc}</p>
                    <p style="margin-top: 30px; color: #666;">You can close this window.</p>
                </body>
                </html>""",
                status=400,
                content_type="text/html",
            )

        # Get authorization code
        code = request.args.get("code")
        if not code:
            logger.error("No authorization code in callback")
            self.result = AuthorizationResult(
                success=False,
                error="missing_code",
                error_description="No authorization code received",
            )
            self._shutdown_event.set()
            return Response(
                """<html>
                <head><title>Authorization Failed</title></head>
                <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px;">
                    <h1 style="color: #d32f2f;">❌ Authorization Failed</h1>
                    <p>No authorization code received from Schwab.</p>
                    <p style="margin-top: 30px; color: #666;">You can close this window.</p>
                </body>
                </html>""",
                status=400,
                content_type="text/html",
            )

        logger.info("Authorization code received successfully")
        self.result = AuthorizationResult(success=True, authorization_code=code)
        self._shutdown_event.set()

        return Response(
            """<html>
            <head><title>Authorization Successful</title></head>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px;">
                <h1 style="color: #4caf50;">✅ Authorization Successful!</h1>
                <p>Your application has been authorized to access your Schwab account.</p>
                <p style="margin-top: 30px; color: #666;">You can close this window and return to the terminal.</p>
            </body>
            </html>""",
            status=200,
            content_type="text/html",
        )

    def _handle_status(self) -> Response:
        """Status endpoint for debugging."""
        return Response(
            '{"status": "running", "waiting_for": "oauth_callback"}',
            status=200,
            content_type="application/json",
        )

    def generate_authorization_url(self) -> str:
        """
        Generate the Schwab authorization URL.

        Returns:
            Complete authorization URL with query parameters
        """
        params = {
            "client_id": self.config.client_id,
            "redirect_uri": self.config.callback_url,
            "response_type": "code",
        }
        url = f"{self.config.authorization_url}?{urlencode(params)}"
        logger.debug(f"Generated authorization URL: {url}")
        return url

    def start(self) -> None:
        """
        Start the callback server in background thread.

        The server runs on HOST machine and listens on all interfaces
        (0.0.0.0) so it can receive callbacks from Schwab via router.

        Raises:
            FileNotFoundError: If SSL certificate files not found
            PermissionError: If cannot bind to port
        """
        # Verify SSL certificates exist
        from pathlib import Path

        cert_path = Path(self.config.ssl_cert_path)
        key_path = Path(self.config.ssl_key_path)

        if not cert_path.exists():
            raise FileNotFoundError(
                f"SSL certificate not found at {cert_path}. "
                f"Ensure Let's Encrypt certificates are installed and accessible."
            )

        if not key_path.exists():
            raise FileNotFoundError(
                f"SSL key not found at {key_path}. "
                f"Ensure Let's Encrypt certificates are installed and accessible."
            )

        # Create SSL context
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(str(cert_path), str(key_path))

        logger.info(
            f"Starting OAuth callback server on port {self.config.callback_port}"
        )
        logger.info(f"Using SSL certificate: {cert_path}")

        # Run Flask in background thread
        def run_server():
            try:
                self.app.run(
                    host="0.0.0.0",  # Listen on all interfaces
                    port=self.config.callback_port,
                    ssl_context=ssl_context,
                    debug=False,
                    use_reloader=False,
                    threaded=True,
                )
            except Exception as e:
                logger.error(f"Server error: {e}")
                self.result = AuthorizationResult(
                    success=False,
                    error="server_error",
                    error_description=f"Server failed to start: {e}",
                )
                self._shutdown_event.set()

        self.server = threading.Thread(target=run_server, daemon=True)
        self.server.start()

        # Give server a moment to start
        time.sleep(2)
        self._server_ready.set()

        logger.info("OAuth callback server started successfully")

    def wait_for_callback(self, timeout: int = 300) -> AuthorizationResult:
        """
        Wait for OAuth callback.

        Args:
            timeout: Maximum seconds to wait (default: 300 = 5 minutes)

        Returns:
            AuthorizationResult with code or error
        """
        logger.info(f"Waiting for OAuth callback (timeout: {timeout}s)")

        if self._shutdown_event.wait(timeout=timeout):
            return self.result or AuthorizationResult(
                success=False,
                error="unknown",
                error_description="Server shutdown without result",
            )
        else:
            logger.warning(f"Timeout waiting for callback after {timeout}s")
            return AuthorizationResult(
                success=False,
                error="timeout",
                error_description=f"No callback received within {timeout} seconds. "
                f"Please ensure you completed the authorization in your browser.",
            )

    def stop(self) -> None:
        """
        Stop the callback server.

        Note: Flask's development server doesn't support graceful shutdown,
        so we rely on the daemon thread terminating when the main program exits.
        """
        if self.server:
            logger.info("OAuth callback server shutting down")
            self._shutdown_event.set()
            # Flask dev server will terminate with main process (daemon thread)


def run_authorization_flow(
    config: SchwabOAuthConfig, open_browser: bool = True, timeout: int = 300
) -> AuthorizationResult:
    """
    Run the complete OAuth authorization flow.

    This function:
    1. Starts HTTPS callback server (on HOST)
    2. Generates authorization URL
    3. Opens browser (or displays URL)
    4. Waits for user to authorize
    5. Returns authorization code or error

    IMPORTANT: Must run on HOST machine (not in devcontainer) to access
    SSL certificates and port 8443.

    Args:
        config: OAuth configuration
        open_browser: Whether to automatically open browser (default: True)
        timeout: Seconds to wait for callback (default: 300)

    Returns:
        AuthorizationResult with authorization code or error

    Raises:
        FileNotFoundError: If SSL certificates not found
        PermissionError: If cannot bind to port
    """
    server = OAuthCallbackServer(config)

    try:
        # Start callback server
        server.start()

        # Generate authorization URL
        auth_url = server.generate_authorization_url()

        # Display banner
        print("\n" + "=" * 70)
        print("SCHWAB OAUTH AUTHORIZATION")
        print("=" * 70)
        print("\n⚠️  IMPORTANT: This script must run on the HOST machine")
        print("   (not inside the devcontainer)\n")
        print("Please authorize the application by visiting:")
        print(f"\n  {auth_url}\n")

        if open_browser:
            print("🌐 Opening browser automatically...")
            try:
                webbrowser.open(auth_url)
            except Exception as e:
                logger.warning(f"Could not open browser automatically: {e}")
                print(f"⚠️  Could not open browser: {e}")
                print("   Please copy the URL above and paste it in your browser.")
        else:
            print("📋 Copy the URL above and paste it in your browser.")

        print("\n⏳ Waiting for authorization...")
        print("   (This window will update when you authorize in your browser)")
        print("=" * 70 + "\n")

        # Wait for callback
        result = server.wait_for_callback(timeout)

        if result.success:
            print("✅ Authorization successful!")
            logger.info("Authorization flow completed successfully")
        else:
            print(f"❌ Authorization failed: {result.error}")
            if result.error_description:
                print(f"   {result.error_description}")
            logger.error(
                f"Authorization flow failed: {result.error} - {result.error_description}"
            )

        return result

    finally:
        server.stop()
