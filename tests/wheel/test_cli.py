"""Tests for wheel CLI commands."""

import os
import tempfile

import pytest
from click.testing import CliRunner

from src.wheel.cli import cli
from src.wheel.manager import WheelManager


@pytest.fixture
def temp_db() -> str:
    """Create a temporary database file."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner()


class TestInitCommand:
    """Tests for 'wheel init' command."""

    def test_init_with_capital_creates_cash_wheel(
        self, runner: CliRunner, temp_db: str
    ) -> None:
        """wheel init --capital should create a wheel in CASH state."""
        result = runner.invoke(
            cli,
            ["--db", temp_db, "init", "AAPL", "--capital", "10000"],
        )

        assert result.exit_code == 0
        assert "Created wheel for AAPL" in result.output
        assert "$10,000.00 capital" in result.output
        assert "cash" in result.output.lower()
        assert "sell puts" in result.output.lower()

    def test_init_with_shares_creates_shares_wheel(
        self, runner: CliRunner, temp_db: str
    ) -> None:
        """wheel init --shares should create a wheel in SHARES state."""
        result = runner.invoke(
            cli,
            [
                "--db", temp_db,
                "init", "AAPL",
                "--shares", "200",
                "--cost-basis", "150.00",
            ],
        )

        assert result.exit_code == 0
        assert "Created wheel for AAPL" in result.output
        assert "200 shares" in result.output
        assert "$150.00" in result.output
        assert "shares" in result.output.lower()
        assert "sell calls" in result.output.lower()

    def test_init_with_both_capital_and_shares(
        self, runner: CliRunner, temp_db: str
    ) -> None:
        """wheel init with both --capital and --shares should work."""
        result = runner.invoke(
            cli,
            [
                "--db", temp_db,
                "init", "AAPL",
                "--capital", "5000",
                "--shares", "100",
                "--cost-basis", "145.00",
            ],
        )

        assert result.exit_code == 0
        assert "100 shares" in result.output
        assert "Additional capital" in result.output
        assert "$5,000.00" in result.output

    def test_init_shares_without_cost_basis_fails(
        self, runner: CliRunner, temp_db: str
    ) -> None:
        """wheel init --shares without --cost-basis should fail."""
        result = runner.invoke(
            cli,
            ["--db", temp_db, "init", "AAPL", "--shares", "100"],
        )

        assert result.exit_code == 1
        assert "cost-basis" in result.output.lower()

    def test_init_without_capital_or_shares_fails(
        self, runner: CliRunner, temp_db: str
    ) -> None:
        """wheel init without --capital or --shares should fail."""
        result = runner.invoke(
            cli,
            ["--db", temp_db, "init", "AAPL"],
        )

        assert result.exit_code == 1
        assert "Must specify" in result.output

    def test_init_with_profile(self, runner: CliRunner, temp_db: str) -> None:
        """wheel init should accept profile option."""
        result = runner.invoke(
            cli,
            [
                "--db", temp_db,
                "init", "AAPL",
                "--capital", "10000",
                "--profile", "aggressive",
            ],
        )

        assert result.exit_code == 0
        assert "aggressive" in result.output.lower()

    def test_init_duplicate_fails(self, runner: CliRunner, temp_db: str) -> None:
        """wheel init should fail for duplicate symbol."""
        runner.invoke(cli, ["--db", temp_db, "init", "AAPL", "--capital", "10000"])
        result = runner.invoke(
            cli, ["--db", temp_db, "init", "AAPL", "--capital", "5000"]
        )

        assert result.exit_code == 1
        assert "already exists" in result.output.lower()


class TestImportCommand:
    """Tests for 'wheel import' command."""

    def test_import_shares(self, runner: CliRunner, temp_db: str) -> None:
        """wheel import should create wheel with shares."""
        result = runner.invoke(
            cli,
            [
                "--db", temp_db,
                "import", "AAPL",
                "--shares", "200",
                "--cost-basis", "150.00",
            ],
        )

        assert result.exit_code == 0
        assert "Imported 200 shares" in result.output
        assert "$150.00" in result.output


class TestRecordCommand:
    """Tests for 'wheel record' command."""

    def test_record_put(self, runner: CliRunner, temp_db: str) -> None:
        """wheel record should record a put trade."""
        # First create the wheel
        runner.invoke(cli, ["--db", temp_db, "init", "AAPL", "--capital", "15000"])

        result = runner.invoke(
            cli,
            [
                "--db", temp_db,
                "record", "AAPL", "put",
                "--strike", "145",
                "--expiration", "2025-02-21",
                "--premium", "1.50",
            ],
        )

        assert result.exit_code == 0
        assert "SELL 1x AAPL $145" in result.output
        assert "PUT" in result.output
        assert "$150.00" in result.output

    def test_record_call(self, runner: CliRunner, temp_db: str) -> None:
        """wheel record should record a call trade."""
        # First import shares
        runner.invoke(
            cli,
            [
                "--db", temp_db,
                "import", "AAPL",
                "--shares", "100",
                "--cost-basis", "150",
            ],
        )

        result = runner.invoke(
            cli,
            [
                "--db", temp_db,
                "record", "AAPL", "call",
                "--strike", "160",
                "--expiration", "2025-02-21",
                "--premium", "1.25",
            ],
        )

        assert result.exit_code == 0
        assert "CALL" in result.output

    def test_record_invalid_state_fails(self, runner: CliRunner, temp_db: str) -> None:
        """wheel record should fail if state doesn't allow trade."""
        # Create wheel in CASH state
        runner.invoke(cli, ["--db", temp_db, "init", "AAPL", "--capital", "10000"])

        # Try to sell call (needs shares)
        result = runner.invoke(
            cli,
            [
                "--db", temp_db,
                "record", "AAPL", "call",
                "--strike", "160",
                "--expiration", "2025-02-21",
                "--premium", "1.25",
            ],
        )

        assert result.exit_code == 1
        assert "Error" in result.output


class TestExpireCommand:
    """Tests for 'wheel expire' command."""

    def test_expire_worthless(self, runner: CliRunner, temp_db: str) -> None:
        """wheel expire should record expiration."""
        runner.invoke(cli, ["--db", temp_db, "init", "AAPL", "--capital", "15000"])
        runner.invoke(
            cli,
            [
                "--db", temp_db,
                "record", "AAPL", "put",
                "--strike", "145",
                "--expiration", "2025-02-21",
                "--premium", "1.50",
            ],
        )

        result = runner.invoke(
            cli, ["--db", temp_db, "expire", "AAPL", "--price", "150"]
        )

        assert result.exit_code == 0
        assert "EXPIRED WORTHLESS" in result.output

    def test_expire_assigned(self, runner: CliRunner, temp_db: str) -> None:
        """wheel expire should handle assignment."""
        runner.invoke(cli, ["--db", temp_db, "init", "AAPL", "--capital", "15000"])
        runner.invoke(
            cli,
            [
                "--db", temp_db,
                "record", "AAPL", "put",
                "--strike", "145",
                "--expiration", "2025-02-21",
                "--premium", "1.50",
            ],
        )

        result = runner.invoke(
            cli, ["--db", temp_db, "expire", "AAPL", "--price", "140"]
        )

        assert result.exit_code == 0
        assert "ASSIGNED" in result.output


class TestStatusCommand:
    """Tests for 'wheel status' command."""

    def test_status_single(self, runner: CliRunner, temp_db: str) -> None:
        """wheel status should show wheel status."""
        runner.invoke(cli, ["--db", temp_db, "init", "AAPL", "--capital", "10000"])

        result = runner.invoke(cli, ["--db", temp_db, "status", "AAPL"])

        assert result.exit_code == 0
        assert "AAPL" in result.output
        assert "cash" in result.output.lower()

    def test_status_all(self, runner: CliRunner, temp_db: str) -> None:
        """wheel status --all should show all wheels."""
        runner.invoke(cli, ["--db", temp_db, "init", "AAPL", "--capital", "10000"])
        runner.invoke(cli, ["--db", temp_db, "init", "MSFT", "--capital", "15000"])

        result = runner.invoke(cli, ["--db", temp_db, "status", "--all"])

        assert result.exit_code == 0
        assert "AAPL" in result.output
        assert "MSFT" in result.output


class TestListCommand:
    """Tests for 'wheel list' command."""

    def test_list_empty(self, runner: CliRunner, temp_db: str) -> None:
        """wheel list should handle empty list."""
        result = runner.invoke(cli, ["--db", temp_db, "list"])

        assert result.exit_code == 0
        assert "No active wheels" in result.output

    def test_list_multiple(self, runner: CliRunner, temp_db: str) -> None:
        """wheel list should show all wheels."""
        runner.invoke(cli, ["--db", temp_db, "init", "AAPL", "--capital", "10000"])
        runner.invoke(cli, ["--db", temp_db, "init", "MSFT", "--capital", "15000"])

        result = runner.invoke(cli, ["--db", temp_db, "list"])

        assert result.exit_code == 0
        assert "AAPL" in result.output
        assert "MSFT" in result.output


class TestPerformanceCommand:
    """Tests for 'wheel performance' command."""

    def test_performance_single(self, runner: CliRunner, temp_db: str) -> None:
        """wheel performance should show metrics."""
        runner.invoke(cli, ["--db", temp_db, "init", "AAPL", "--capital", "15000"])
        runner.invoke(
            cli,
            [
                "--db", temp_db,
                "record", "AAPL", "put",
                "--strike", "145",
                "--expiration", "2025-02-21",
                "--premium", "1.50",
            ],
        )
        runner.invoke(cli, ["--db", temp_db, "expire", "AAPL", "--price", "150"])

        result = runner.invoke(cli, ["--db", temp_db, "performance", "AAPL"])

        assert result.exit_code == 0
        assert "Total Premium" in result.output
        assert "$150" in result.output

    def test_performance_export_csv(self, runner: CliRunner, temp_db: str) -> None:
        """wheel performance --export csv should output CSV."""
        runner.invoke(cli, ["--db", temp_db, "init", "AAPL", "--capital", "15000"])
        runner.invoke(
            cli,
            [
                "--db", temp_db,
                "record", "AAPL", "put",
                "--strike", "145",
                "--expiration", "2025-02-21",
                "--premium", "1.50",
            ],
        )
        runner.invoke(cli, ["--db", temp_db, "expire", "AAPL", "--price", "150"])

        result = runner.invoke(
            cli, ["--db", temp_db, "performance", "AAPL", "--export", "csv"]
        )

        assert result.exit_code == 0
        assert "symbol,direction" in result.output
        assert "AAPL,put" in result.output


class TestHistoryCommand:
    """Tests for 'wheel history' command."""

    def test_history_shows_trades(self, runner: CliRunner, temp_db: str) -> None:
        """wheel history should show trade history."""
        runner.invoke(cli, ["--db", temp_db, "init", "AAPL", "--capital", "15000"])
        runner.invoke(
            cli,
            [
                "--db", temp_db,
                "record", "AAPL", "put",
                "--strike", "145",
                "--expiration", "2025-02-21",
                "--premium", "1.50",
            ],
        )
        runner.invoke(cli, ["--db", temp_db, "expire", "AAPL", "--price", "150"])

        result = runner.invoke(cli, ["--db", temp_db, "history", "AAPL"])

        assert result.exit_code == 0
        assert "PUT" in result.output
        assert "145" in result.output
        assert "[WIN]" in result.output


class TestArchiveCommand:
    """Tests for 'wheel archive' command."""

    def test_archive_wheel(self, runner: CliRunner, temp_db: str) -> None:
        """wheel archive should deactivate wheel."""
        runner.invoke(cli, ["--db", temp_db, "init", "AAPL", "--capital", "10000"])

        result = runner.invoke(cli, ["--db", temp_db, "archive", "AAPL"])

        assert result.exit_code == 0
        assert "Archived" in result.output

        # Verify it's gone from list
        list_result = runner.invoke(cli, ["--db", temp_db, "list"])
        assert "AAPL" not in list_result.output

    def test_archive_with_open_position_fails(
        self, runner: CliRunner, temp_db: str
    ) -> None:
        """wheel archive should fail with open position."""
        runner.invoke(cli, ["--db", temp_db, "init", "AAPL", "--capital", "15000"])
        runner.invoke(
            cli,
            [
                "--db", temp_db,
                "record", "AAPL", "put",
                "--strike", "145",
                "--expiration", "2025-02-21",
                "--premium", "1.50",
            ],
        )

        result = runner.invoke(cli, ["--db", temp_db, "archive", "AAPL"])

        assert result.exit_code == 1
        assert "Error" in result.output
