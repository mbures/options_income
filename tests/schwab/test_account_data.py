"""Tests for Schwab account data endpoints."""

from unittest import mock

import pytest

from src.schwab.client import SchwabClient
from src.schwab.models import SchwabAccount, SchwabAccountBalances, SchwabPosition


class TestAccountDataEndpoints:
    """Tests for account data methods."""

    @pytest.fixture
    def mock_oauth(self):
        """Create mock OAuth coordinator."""
        oauth = mock.Mock()
        oauth.get_authorization_header.return_value = {
            "Authorization": "Bearer test_token"
        }
        return oauth

    @pytest.fixture
    def client(self, mock_oauth):
        """Create Schwab client with mocked OAuth."""
        return SchwabClient(oauth_coordinator=mock_oauth, enable_cache=False)

    @pytest.fixture
    def mock_accounts_response(self):
        """Mock Schwab accounts response."""
        return [
            {
                "securitiesAccount": {
                    "accountNumber": "ABC123456789",
                    "type": "MARGIN",
                    "nickname": "Trading Account",
                    "isClosingOnlyRestricted": False,
                    "isDayTrader": False,
                    "currentBalances": {
                        "cashBalance": 10000.00,
                        "cashAvailableForTrading": 9500.00,
                        "cashAvailableForWithdrawal": 9000.00,
                        "liquidationValue": 50000.00,
                        "totalCash": 10000.00,
                        "buyingPower": 40000.00,
                    },
                }
            },
            {
                "securitiesAccount": {
                    "accountNumber": "XYZ987654321",
                    "type": "CASH",
                    "nickname": "IRA Account",
                    "isClosingOnlyRestricted": False,
                    "isDayTrader": False,
                    "currentBalances": {
                        "cashBalance": 25000.00,
                        "cashAvailableForTrading": 25000.00,
                        "cashAvailableForWithdrawal": 0.00,
                        "liquidationValue": 75000.00,
                        "totalCash": 25000.00,
                        "buyingPower": 25000.00,
                    },
                }
            },
        ]

    @pytest.fixture
    def mock_account_with_positions_response(self):
        """Mock Schwab account details with positions response."""
        return {
            "securitiesAccount": {
                "accountNumber": "ABC123456789",
                "type": "MARGIN",
                "nickname": "Trading Account",
                "isClosingOnlyRestricted": False,
                "isDayTrader": False,
                "currentBalances": {
                    "cashBalance": 10000.00,
                    "cashAvailableForTrading": 9500.00,
                    "cashAvailableForWithdrawal": 9000.00,
                    "liquidationValue": 50000.00,
                    "totalCash": 10000.00,
                    "buyingPower": 40000.00,
                },
                "positions": [
                    {
                        "instrument": {
                            "symbol": "AAPL",
                            "assetType": "EQUITY",
                            "instrumentType": "EQUITY",
                        },
                        "longQuantity": 100.0,
                        "shortQuantity": 0.0,
                        "averagePrice": 150.00,
                        "marketValue": 16000.00,
                        "currentDayProfitLoss": 100.00,
                        "currentDayProfitLossPercentage": 0.625,
                    },
                    {
                        "instrument": {
                            "symbol": "AAPL_022126P145",
                            "assetType": "OPTION",
                            "instrumentType": "OPTION",
                        },
                        "longQuantity": 0.0,
                        "shortQuantity": -5.0,
                        "averagePrice": 1.80,
                        "marketValue": -900.00,
                        "currentDayProfitLoss": -50.00,
                        "currentDayProfitLossPercentage": 5.88,
                    },
                ],
            }
        }

    @mock.patch("src.schwab.client.requests.Session.request")
    def test_get_accounts_success(self, mock_request, client, mock_accounts_response):
        """get_accounts() returns list of accounts successfully."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = mock_accounts_response
        mock_request.return_value = mock_response

        accounts = client.get_accounts()

        assert len(accounts) == 2
        assert all(isinstance(account, SchwabAccount) for account in accounts)

        # Check first account
        account1 = accounts[0]
        assert account1.account_number == "ABC123456789"
        assert account1.account_type == "MARGIN"
        assert account1.account_nickname == "Trading Account"
        assert account1.is_closing_only is False
        assert account1.is_day_trader is False

        # Check balances
        assert account1.balances.cash_balance == 10000.00
        assert account1.balances.account_value == 50000.00
        assert account1.balances.buying_power == 40000.00

        # Check second account
        account2 = accounts[1]
        assert account2.account_number == "XYZ987654321"
        assert account2.account_type == "CASH"
        assert account2.account_nickname == "IRA Account"

    @mock.patch("src.schwab.client.requests.Session.request")
    def test_get_account_positions_success(
        self, mock_request, client, mock_account_with_positions_response
    ):
        """get_account_positions() returns account with positions successfully."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = mock_account_with_positions_response
        mock_request.return_value = mock_response

        account = client.get_account_positions("ABC123456789")

        assert isinstance(account, SchwabAccount)
        assert account.account_number == "ABC123456789"
        assert len(account.positions) == 2

        # Check equity position
        equity_position = account.positions[0]
        assert equity_position.symbol == "AAPL"
        assert equity_position.quantity == 100.0
        assert equity_position.average_price == 150.00
        assert equity_position.market_value == 16000.00
        assert equity_position.day_gain == 100.00
        assert equity_position.asset_type == "EQUITY"

        # Check option position
        option_position = account.positions[1]
        assert option_position.symbol == "AAPL_022126P145"
        assert option_position.quantity == -5.0
        assert option_position.average_price == 1.80
        assert option_position.market_value == -900.00
        assert option_position.asset_type == "OPTION"

    @mock.patch("src.schwab.client.requests.Session.request")
    def test_get_account_positions_sends_correct_params(self, mock_request, client):
        """get_account_positions() sends correct API parameters."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = {
            "securitiesAccount": {
                "accountNumber": "ABC123",
                "type": "CASH",
                "currentBalances": {
                    "cashBalance": 1000.00,
                    "cashAvailableForTrading": 1000.00,
                    "cashAvailableForWithdrawal": 1000.00,
                    "liquidationValue": 1000.00,
                    "totalCash": 1000.00,
                },
                "positions": [],
            }
        }
        mock_request.return_value = mock_response

        client.get_account_positions("ABC123")

        # Check request parameters
        call_kwargs = mock_request.call_args[1]
        params = call_kwargs.get("params", {})
        assert params.get("fields") == "positions"

        # Check endpoint URL
        assert "ABC123" in mock_request.call_args[0][1]

    def test_parse_schwab_account(self, client):
        """_parse_schwab_account() correctly parses account data."""
        account_data = {
            "securitiesAccount": {
                "accountNumber": "TEST123",
                "type": "MARGIN",
                "nickname": "Test Account",
                "isClosingOnlyRestricted": True,
                "isDayTrader": True,
                "currentBalances": {
                    "cashBalance": 5000.00,
                    "cashAvailableForTrading": 4500.00,
                    "cashAvailableForWithdrawal": 4000.00,
                    "liquidationValue": 25000.00,
                    "totalCash": 5000.00,
                    "buyingPower": 20000.00,
                },
                "positions": [],
            }
        }

        account = client._parse_schwab_account(account_data)

        assert account.account_number == "TEST123"
        assert account.account_type == "MARGIN"
        assert account.account_nickname == "Test Account"
        assert account.is_closing_only is True
        assert account.is_day_trader is True
        assert account.balances.cash_balance == 5000.00
        assert len(account.positions) == 0

    def test_parse_schwab_position(self, client):
        """_parse_schwab_position() correctly parses position data."""
        position_data = {
            "instrument": {
                "symbol": "TSLA",
                "assetType": "EQUITY",
                "instrumentType": "EQUITY",
            },
            "longQuantity": 50.0,
            "shortQuantity": 0.0,
            "averagePrice": 200.00,
            "marketValue": 12000.00,
            "currentDayProfitLoss": 500.00,
            "currentDayProfitLossPercentage": 4.35,
        }

        position = client._parse_schwab_position(position_data)

        assert position.symbol == "TSLA"
        assert position.quantity == 50.0
        assert position.average_price == 200.00
        assert position.market_value == 12000.00
        assert position.day_gain == 500.00
        assert position.asset_type == "EQUITY"
        assert position.total_gain == 2000.00  # 12000 - (200 * 50)

    def test_parse_schwab_balances(self, client):
        """_parse_schwab_balances() correctly parses balance data."""
        balance_data = {
            "cashBalance": 15000.00,
            "cashAvailableForTrading": 14500.00,
            "cashAvailableForWithdrawal": 14000.00,
            "liquidationValue": 60000.00,
            "totalCash": 15000.00,
            "buyingPower": 50000.00,
        }

        balances = client._parse_schwab_balances(balance_data)

        assert balances.cash_balance == 15000.00
        assert balances.cash_available_for_trading == 14500.00
        assert balances.cash_available_for_withdrawal == 14000.00
        assert balances.market_value == 60000.00
        assert balances.total_cash == 15000.00
        assert balances.account_value == 60000.00
        assert balances.buying_power == 50000.00

    def test_schwab_account_get_equity_positions(self, client):
        """SchwabAccount.get_equity_positions() filters equity positions."""
        account = SchwabAccount(
            account_number="TEST",
            account_type="CASH",
            positions=[
                SchwabPosition(
                    symbol="AAPL",
                    quantity=100,
                    average_price=150,
                    current_price=160,
                    market_value=16000,
                    asset_type="EQUITY",
                ),
                SchwabPosition(
                    symbol="AAPL_022126P145",
                    quantity=-5,
                    average_price=1.80,
                    current_price=1.70,
                    market_value=-850,
                    asset_type="OPTION",
                ),
            ],
            balances=SchwabAccountBalances(
                cash_balance=1000,
                cash_available_for_trading=1000,
                cash_available_for_withdrawal=1000,
                market_value=1000,
                total_cash=1000,
                account_value=1000,
            ),
        )

        equity_positions = account.get_equity_positions()

        assert len(equity_positions) == 1
        assert equity_positions[0].symbol == "AAPL"
        assert equity_positions[0].asset_type == "EQUITY"

    def test_schwab_account_get_option_positions(self, client):
        """SchwabAccount.get_option_positions() filters option positions."""
        account = SchwabAccount(
            account_number="TEST",
            account_type="CASH",
            positions=[
                SchwabPosition(
                    symbol="AAPL",
                    quantity=100,
                    average_price=150,
                    current_price=160,
                    market_value=16000,
                    asset_type="EQUITY",
                ),
                SchwabPosition(
                    symbol="AAPL_022126P145",
                    quantity=-5,
                    average_price=1.80,
                    current_price=1.70,
                    market_value=-850,
                    asset_type="OPTION",
                ),
            ],
            balances=SchwabAccountBalances(
                cash_balance=1000,
                cash_available_for_trading=1000,
                cash_available_for_withdrawal=1000,
                market_value=1000,
                total_cash=1000,
                account_value=1000,
            ),
        )

        option_positions = account.get_option_positions()

        assert len(option_positions) == 1
        assert option_positions[0].symbol == "AAPL_022126P145"
        assert option_positions[0].asset_type == "OPTION"

    def test_schwab_account_get_position(self, client):
        """SchwabAccount.get_position() retrieves position by symbol."""
        account = SchwabAccount(
            account_number="TEST",
            account_type="CASH",
            positions=[
                SchwabPosition(
                    symbol="AAPL",
                    quantity=100,
                    average_price=150,
                    current_price=160,
                    market_value=16000,
                    asset_type="EQUITY",
                ),
                SchwabPosition(
                    symbol="TSLA",
                    quantity=50,
                    average_price=200,
                    current_price=210,
                    market_value=10500,
                    asset_type="EQUITY",
                ),
            ],
            balances=SchwabAccountBalances(
                cash_balance=1000,
                cash_available_for_trading=1000,
                cash_available_for_withdrawal=1000,
                market_value=1000,
                total_cash=1000,
                account_value=1000,
            ),
        )

        position = account.get_position("TSLA")

        assert position is not None
        assert position.symbol == "TSLA"
        assert position.quantity == 50

        # Test non-existent position
        position = account.get_position("MSFT")
        assert position is None
