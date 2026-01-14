"""Unit tests for options service layer."""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timezone
from src.models import OptionContract, OptionsChain
from src.options_service import OptionsChainService, DataValidationError
from src.finnhub_client import FinnhubAPIError


class TestOptionsChainService:
    """Test suite for OptionsChainService class."""

    @pytest.fixture
    def mock_client(self):
        """Create mock Finnhub client."""
        return Mock()

    @pytest.fixture
    def service(self, mock_client):
        """Create test service."""
        return OptionsChainService(mock_client)

    @pytest.fixture
    def sample_api_response(self):
        """Sample API response data."""
        return {
            "data": [
                {
                    "strike": 10.0,
                    "expirationDate": "2026-01-16",
                    "type": "Call",
                    "bid": 1.25,
                    "ask": 1.30,
                    "last": 1.27,
                    "volume": 1500,
                    "openInterest": 5000,
                    "delta": 0.55,
                    "gamma": 0.08
                },
                {
                    "strike": 10.0,
                    "expirationDate": "2026-01-16",
                    "type": "Put",
                    "bid": 0.85,
                    "ask": 0.90,
                    "last": 0.87,
                    "volume": 1200,
                    "openInterest": 4500
                }
            ]
        }

    def test_service_initialization(self, mock_client):
        """Test service initialization."""
        service = OptionsChainService(mock_client)
        assert service.client == mock_client

    def test_get_options_chain_success(self, service, mock_client, sample_api_response):
        """Test successful options chain retrieval."""
        mock_client.get_option_chain.return_value = sample_api_response

        result = service.get_options_chain("F")

        assert isinstance(result, OptionsChain)
        assert result.symbol == "F"
        assert len(result.contracts) == 2
        assert result.retrieved_at is not None
        mock_client.get_option_chain.assert_called_once_with("F")

    def test_get_options_chain_normalizes_symbol(self, service, mock_client, sample_api_response):
        """Test that symbol is normalized to uppercase."""
        mock_client.get_option_chain.return_value = sample_api_response

        result = service.get_options_chain("aapl")

        assert result.symbol == "AAPL"

    def test_get_options_chain_parses_contracts_correctly(
        self,
        service,
        mock_client,
        sample_api_response
    ):
        """Test that contracts are parsed correctly."""
        mock_client.get_option_chain.return_value = sample_api_response

        result = service.get_options_chain("F")

        # Check first contract (Call)
        call = result.contracts[0]
        assert call.symbol == "F"
        assert call.strike == 10.0
        assert call.expiration_date == "2026-01-16"
        assert call.option_type == "Call"
        assert call.bid == 1.25
        assert call.ask == 1.30
        assert call.last == 1.27
        assert call.volume == 1500
        assert call.open_interest == 5000
        assert call.delta == 0.55
        assert call.gamma == 0.08

        # Check second contract (Put)
        put = result.contracts[1]
        assert put.option_type == "Put"
        assert put.bid == 0.85

    def test_get_options_chain_api_error(self, service, mock_client):
        """Test handling of API errors."""
        mock_client.get_option_chain.side_effect = FinnhubAPIError("API Error")

        with pytest.raises(FinnhubAPIError):
            service.get_options_chain("F")

    def test_validate_response_success(self, service):
        """Test validation of valid response."""
        valid_response = {"data": [{"strike": 10.0}]}
        
        # Should not raise exception
        service._validate_response(valid_response)

    def test_validate_response_not_dict(self, service):
        """Test validation fails for non-dict response."""
        with pytest.raises(DataValidationError, match="not a dictionary"):
            service._validate_response("not a dict")

    def test_validate_response_empty(self, service):
        """Test validation fails for empty response."""
        with pytest.raises(DataValidationError, match="Empty response"):
            service._validate_response({})

    def test_validate_response_with_error(self, service):
        """Test validation fails when response contains error."""
        with pytest.raises(DataValidationError, match="API returned error"):
            service._validate_response({"error": "Invalid symbol"})

    def test_parse_contracts_with_data_key(self, service, sample_api_response):
        """Test parsing contracts from response with 'data' key."""
        contracts = service._parse_contracts(sample_api_response, "F")

        assert len(contracts) == 2
        assert all(isinstance(c, OptionContract) for c in contracts)

    def test_parse_contracts_as_direct_list(self, service):
        """Test parsing contracts when response is direct list."""
        response = [
            {
                "strike": 10.0,
                "expirationDate": "2026-01-16",
                "type": "Call",
                "bid": 1.25,
                "ask": 1.30
            }
        ]

        contracts = service._parse_contracts(response, "F")

        assert len(contracts) == 1

    def test_parse_contracts_handles_parsing_errors(self, service):
        """Test that individual parsing errors don't fail entire operation."""
        response = {
            "data": [
                {
                    "strike": 10.0,
                    "expirationDate": "2026-01-16",
                    "type": "Call",
                    "bid": 1.25,
                    "ask": 1.30
                },
                {
                    # Missing required field 'strike'
                    "expirationDate": "2026-01-16",
                    "type": "Put"
                },
                {
                    "strike": 11.0,
                    "expirationDate": "2026-01-16",
                    "type": "Call",
                    "bid": 0.75,
                    "ask": 0.80
                }
            ]
        }

        contracts = service._parse_contracts(response, "F")

        # Should successfully parse 2 out of 3 contracts
        assert len(contracts) == 2

    def test_parse_contracts_all_invalid(self, service):
        """Test that error is raised when all contracts fail to parse."""
        response = {
            "data": [
                {"invalid": "data"},
                {"also": "invalid"}
            ]
        }

        with pytest.raises(DataValidationError, match="No valid contracts found"):
            service._parse_contracts(response, "F")

    def test_parse_single_contract_required_fields(self, service):
        """Test parsing with only required fields."""
        data = {
            "strike": 10.0,
            "expirationDate": "2026-01-16",
            "type": "Call"
        }

        contract = service._parse_single_contract(data, "F")

        assert contract.symbol == "F"
        assert contract.strike == 10.0
        assert contract.expiration_date == "2026-01-16"
        assert contract.option_type == "Call"
        assert contract.bid is None
        assert contract.ask is None

    def test_parse_single_contract_all_fields(self, service):
        """Test parsing with all fields."""
        data = {
            "strike": 10.0,
            "expirationDate": "2026-01-16",
            "type": "Call",
            "bid": 1.25,
            "ask": 1.30,
            "last": 1.27,
            "volume": 1500,
            "openInterest": 5000,
            "delta": 0.55,
            "gamma": 0.08,
            "theta": -0.05,
            "vega": 0.12,
            "rho": 0.03,
            "impliedVolatility": 0.35
        }

        contract = service._parse_single_contract(data, "F")

        assert contract.bid == 1.25
        assert contract.volume == 1500
        assert contract.delta == 0.55
        assert contract.implied_volatility == 0.35

    def test_parse_single_contract_invalid_option_type(self, service):
        """Test that invalid option type raises error."""
        data = {
            "strike": 10.0,
            "expirationDate": "2026-01-16",
            "type": "Invalid"
        }

        with pytest.raises(ValueError, match="Invalid option type"):
            service._parse_single_contract(data, "F")

    def test_parse_single_contract_missing_required_field(self, service):
        """Test that missing required field raises error."""
        data = {
            "expirationDate": "2026-01-16",
            "type": "Call"
            # Missing 'strike'
        }

        with pytest.raises(KeyError):
            service._parse_single_contract(data, "F")

    def test_safe_float_valid(self, service):
        """Test safe float conversion with valid values."""
        assert service._safe_float(1.5) == 1.5
        assert service._safe_float("2.5") == 2.5
        assert service._safe_float(3) == 3.0

    def test_safe_float_invalid(self, service):
        """Test safe float conversion with invalid values."""
        assert service._safe_float(None) is None
        assert service._safe_float("invalid") is None
        assert service._safe_float("") is None

    def test_safe_int_valid(self, service):
        """Test safe int conversion with valid values."""
        assert service._safe_int(10) == 10
        assert service._safe_int("20") == 20
        assert service._safe_int(3.7) == 3

    def test_safe_int_invalid(self, service):
        """Test safe int conversion with invalid values."""
        assert service._safe_int(None) is None
        assert service._safe_int("invalid") is None
        assert service._safe_int("") is None

    def test_extract_contracts_from_response(self, service):
        """Test extraction of contracts from alternate structures."""
        # Test with 'options' key
        response1 = {
            "options": [
                {"strike": 10.0, "expirationDate": "2026-01-16", "type": "Call"}
            ]
        }
        contracts1 = service._extract_contracts_from_response(response1)
        assert len(contracts1) == 1

        # Test with nested structure
        response2 = {
            "chain": {
                "2026-01-16": [
                    {"strike": 10.0, "expirationDate": "2026-01-16", "type": "Call"}
                ]
            }
        }
        contracts2 = service._extract_contracts_from_response(response2)
        assert len(contracts2) == 1

    def test_timestamp_format(self, service, mock_client, sample_api_response):
        """Test that retrieved_at timestamp is in ISO format."""
        mock_client.get_option_chain.return_value = sample_api_response

        result = service.get_options_chain("F")

        # Verify timestamp is valid ISO format
        try:
            datetime.fromisoformat(result.retrieved_at.replace('Z', '+00:00'))
        except ValueError:
            pytest.fail("Timestamp is not in valid ISO format")

    def test_get_options_chain_counts_contracts(
        self,
        service,
        mock_client,
        sample_api_response
    ):
        """Test that service correctly counts calls and puts."""
        mock_client.get_option_chain.return_value = sample_api_response

        result = service.get_options_chain("F")

        calls = [c for c in result.contracts if c.is_call]
        puts = [c for c in result.contracts if c.is_put]

        assert len(calls) == 1
        assert len(puts) == 1
