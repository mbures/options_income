"""Tests for CLI API mode with fallback to direct mode.

This module tests that CLI commands work correctly in both API mode
and direct mode, and that fallback behavior works as expected.
"""

import pytest
from click.testing import CliRunner

from src.wheel.cli import cli
from src.wheel.api_client import WheelStrategyAPIClient


@pytest.fixture
def cli_runner():
    """Create Click CLI test runner.

    Returns:
        CliRunner instance
    """
    return CliRunner()


@pytest.fixture
def test_db_path(tmp_path):
    """Create temporary database path.

    Args:
        tmp_path: Pytest temporary path fixture

    Returns:
        Path to temporary database file
    """
    return str(tmp_path / "test_trades.db")


class TestCLIAPIMode:
    """Tests for CLI in API mode."""

    def test_cli_loads_with_api_unavailable(self, cli_runner, test_db_path):
        """Test CLI loads successfully when API is unavailable.

        Should fall back to direct mode gracefully.

        Args:
            cli_runner: Click test runner
            test_db_path: Path to test database
        """
        # Run a simple command with API mode enabled but server not running
        result = cli_runner.invoke(
            cli,
            ["--db", test_db_path, "--api-mode", "--verbose", "list"],
            catch_exceptions=False,
        )

        # Should not crash - should fall back to direct mode
        assert "API unavailable" in result.output or "No active wheels" in result.output

    def test_cli_direct_mode_forced(self, cli_runner, test_db_path):
        """Test CLI in forced direct mode.

        Args:
            cli_runner: Click test runner
            test_db_path: Path to test database
        """
        result = cli_runner.invoke(
            cli,
            ["--db", test_db_path, "--direct-mode", "list"],
            catch_exceptions=False,
        )

        # Should work in direct mode
        assert result.exit_code == 0
        assert "No active wheels" in result.output

    def test_init_command_direct_mode(self, cli_runner, test_db_path):
        """Test wheel init command in direct mode.

        Args:
            cli_runner: Click test runner
            test_db_path: Path to test database
        """
        result = cli_runner.invoke(
            cli,
            [
                "--db",
                test_db_path,
                "--direct-mode",
                "init",
                "AAPL",
                "--capital",
                "10000",
            ],
            catch_exceptions=False,
        )

        # Should succeed
        assert result.exit_code == 0
        assert "Created wheel for AAPL" in result.output
        assert "$10,000.00 capital" in result.output

    def test_list_command_direct_mode(self, cli_runner, test_db_path):
        """Test wheel list command in direct mode.

        Args:
            cli_runner: Click test runner
            test_db_path: Path to test database
        """
        # First create a wheel
        cli_runner.invoke(
            cli,
            [
                "--db",
                test_db_path,
                "--direct-mode",
                "init",
                "AAPL",
                "--capital",
                "10000",
            ],
        )

        # List wheels
        result = cli_runner.invoke(
            cli,
            ["--db", test_db_path, "--direct-mode", "list"],
            catch_exceptions=False,
        )

        # Should show the wheel
        assert result.exit_code == 0
        assert "AAPL" in result.output
        assert "Total wheels: 1" in result.output

    def test_status_command_direct_mode(self, cli_runner, test_db_path):
        """Test wheel status command in direct mode.

        Args:
            cli_runner: Click test runner
            test_db_path: Path to test database
        """
        # First create a wheel
        cli_runner.invoke(
            cli,
            [
                "--db",
                test_db_path,
                "--direct-mode",
                "init",
                "AAPL",
                "--capital",
                "10000",
            ],
        )

        # Get status
        result = cli_runner.invoke(
            cli,
            ["--db", test_db_path, "--direct-mode", "status", "AAPL"],
            catch_exceptions=False,
        )

        # Should show wheel status
        assert result.exit_code == 0
        assert "AAPL" in result.output
        assert "State:" in result.output

    def test_error_handling_symbol_not_found(self, cli_runner, test_db_path):
        """Test error handling when symbol not found.

        Args:
            cli_runner: Click test runner
            test_db_path: Path to test database
        """
        result = cli_runner.invoke(
            cli,
            ["--db", test_db_path, "--direct-mode", "status", "INVALID"],
        )

        # Should fail gracefully
        assert result.exit_code == 1
        assert "No wheel found for INVALID" in result.output


class TestCLIFallback:
    """Tests for CLI fallback from API mode to direct mode."""

    def test_fallback_on_connection_error(self, cli_runner, test_db_path):
        """Test fallback when API connection fails.

        Args:
            cli_runner: Click test runner
            test_db_path: Path to test database
        """
        # Create a wheel in direct mode first
        cli_runner.invoke(
            cli,
            [
                "--db",
                test_db_path,
                "--direct-mode",
                "init",
                "AAPL",
                "--capital",
                "10000",
            ],
        )

        # Try to list with API mode (should fall back)
        result = cli_runner.invoke(
            cli,
            ["--db", test_db_path, "--api-mode", "--verbose", "list"],
            catch_exceptions=False,
        )

        # Should fall back and show the wheel
        assert "AAPL" in result.output or "API unavailable" in result.output


class TestCLIOutputCompatibility:
    """Tests that output format is consistent between modes."""

    def test_init_output_format(self, cli_runner, test_db_path):
        """Test that init command output format is consistent.

        Args:
            cli_runner: Click test runner
            test_db_path: Path to test database
        """
        result = cli_runner.invoke(
            cli,
            [
                "--db",
                test_db_path,
                "--direct-mode",
                "init",
                "AAPL",
                "--capital",
                "15000",
            ],
            catch_exceptions=False,
        )

        # Check output format
        assert "Created wheel for AAPL" in result.output
        assert "15,000" in result.output
        assert "Profile:" in result.output
        assert "State:" in result.output

    def test_list_output_format(self, cli_runner, test_db_path):
        """Test that list command output format is consistent.

        Args:
            cli_runner: Click test runner
            test_db_path: Path to test database
        """
        # Create multiple wheels
        cli_runner.invoke(
            cli,
            ["--db", test_db_path, "--direct-mode", "init", "AAPL", "--capital", "10000"],
        )
        cli_runner.invoke(
            cli,
            ["--db", test_db_path, "--direct-mode", "init", "MSFT", "--capital", "15000"],
        )

        result = cli_runner.invoke(
            cli,
            ["--db", test_db_path, "--direct-mode", "list"],
            catch_exceptions=False,
        )

        # Check output format
        assert "Symbol" in result.output
        assert "State" in result.output
        assert "AAPL" in result.output
        assert "MSFT" in result.output
        assert "Total wheels: 2" in result.output


class TestCLIPortfolioCommands:
    """Tests for portfolio management commands."""

    def test_portfolio_commands_require_api_mode(self, cli_runner, test_db_path):
        """Test that portfolio commands require API mode.

        Args:
            cli_runner: Click test runner
            test_db_path: Path to test database
        """
        # Try to list portfolios in direct mode
        result = cli_runner.invoke(
            cli,
            ["--db", test_db_path, "--direct-mode", "portfolio", "list"],
        )

        # Should fail with helpful message
        assert result.exit_code == 1
        assert "requires API mode" in result.output

    def test_portfolio_list_with_api_unavailable(self, cli_runner, test_db_path):
        """Test portfolio list when API is unavailable.

        Args:
            cli_runner: Click test runner
            test_db_path: Path to test database
        """
        # Try to list portfolios with API mode but server not running
        result = cli_runner.invoke(
            cli,
            ["--db", test_db_path, "--api-mode", "portfolio", "list"],
        )

        # Should fail gracefully with message about API mode requirement
        assert result.exit_code == 1
        assert "requires API mode" in result.output or "API unavailable" in result.output


class TestCLIValidation:
    """Tests for CLI input validation."""

    def test_init_requires_capital_or_shares(self, cli_runner, test_db_path):
        """Test that init requires either capital or shares.

        Args:
            cli_runner: Click test runner
            test_db_path: Path to test database
        """
        result = cli_runner.invoke(
            cli,
            ["--db", test_db_path, "--direct-mode", "init", "AAPL"],
        )

        # Should fail with validation error
        assert result.exit_code == 1
        assert "Must specify --capital and/or --shares" in result.output

    def test_init_shares_requires_cost_basis(self, cli_runner, test_db_path):
        """Test that shares option requires cost basis.

        Args:
            cli_runner: Click test runner
            test_db_path: Path to test database
        """
        result = cli_runner.invoke(
            cli,
            ["--db", test_db_path, "--direct-mode", "init", "AAPL", "--shares", "100"],
        )

        # Should fail with validation error
        assert result.exit_code == 1
        assert "--cost-basis is required" in result.output


class TestCLIHelp:
    """Tests for CLI help text."""

    def test_main_help(self, cli_runner):
        """Test main CLI help text.

        Args:
            cli_runner: Click test runner
        """
        result = cli_runner.invoke(cli, ["--help"])

        # Should show help
        assert result.exit_code == 0
        assert "Wheel Strategy Tool" in result.output
        assert "--api-url" in result.output
        assert "--api-mode" in result.output

    def test_portfolio_help(self, cli_runner):
        """Test portfolio command help text.

        Args:
            cli_runner: Click test runner
        """
        result = cli_runner.invoke(cli, ["portfolio", "--help"])

        # Should show portfolio help
        assert result.exit_code == 0
        assert "Manage portfolios" in result.output
        assert "create" in result.output
        assert "list" in result.output

    def test_init_help(self, cli_runner):
        """Test init command help text.

        Args:
            cli_runner: Click test runner
        """
        result = cli_runner.invoke(cli, ["init", "--help"])

        # Should show init help
        assert result.exit_code == 0
        assert "Initialize a new wheel position" in result.output
        assert "--capital" in result.output
        assert "--shares" in result.output
        assert "--portfolio" in result.output


@pytest.mark.integration
class TestCLIWithMockAPI:
    """Integration tests with mock API server."""

    # These tests would require a running test API server
    # Skipping for now, but structure is here for future implementation

    def test_init_via_api(self):
        """Test init command via API mode."""
        pytest.skip("Requires test API server")

    def test_record_trade_via_api(self):
        """Test record trade via API mode."""
        pytest.skip("Requires test API server")

    def test_fallback_on_api_failure(self):
        """Test fallback when API fails during operation."""
        pytest.skip("Requires test API server")
