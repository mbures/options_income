"""Unit tests for data models."""

import pytest
from src.models import OptionContract, OptionsChain


class TestOptionContract:
    """Test suite for OptionContract class."""

    def test_option_contract_initialization(self):
        """Test basic contract initialization."""
        contract = OptionContract(
            symbol="F",
            strike=10.0,
            expiration_date="2026-01-16",
            option_type="Call",
            bid=1.25,
            ask=1.30
        )
        
        assert contract.symbol == "F"
        assert contract.strike == 10.0
        assert contract.expiration_date == "2026-01-16"
        assert contract.option_type == "Call"
        assert contract.bid == 1.25
        assert contract.ask == 1.30

    def test_option_contract_with_all_fields(self):
        """Test contract with all optional fields."""
        contract = OptionContract(
            symbol="AAPL",
            strike=150.0,
            expiration_date="2026-02-20",
            option_type="Put",
            bid=5.50,
            ask=5.60,
            last=5.55,
            volume=1000,
            open_interest=5000,
            delta=-0.45,
            gamma=0.08,
            theta=-0.05,
            vega=0.12,
            rho=-0.03,
            implied_volatility=0.35
        )
        
        assert contract.last == 5.55
        assert contract.volume == 1000
        assert contract.open_interest == 5000
        assert contract.delta == -0.45
        assert contract.gamma == 0.08
        assert contract.theta == -0.05
        assert contract.vega == 0.12
        assert contract.rho == -0.03
        assert contract.implied_volatility == 0.35

    def test_is_call_property(self):
        """Test is_call property."""
        call = OptionContract(
            symbol="F",
            strike=10.0,
            expiration_date="2026-01-16",
            option_type="Call"
        )
        put = OptionContract(
            symbol="F",
            strike=10.0,
            expiration_date="2026-01-16",
            option_type="Put"
        )
        
        assert call.is_call is True
        assert put.is_call is False

    def test_is_put_property(self):
        """Test is_put property."""
        call = OptionContract(
            symbol="F",
            strike=10.0,
            expiration_date="2026-01-16",
            option_type="Call"
        )
        put = OptionContract(
            symbol="F",
            strike=10.0,
            expiration_date="2026-01-16",
            option_type="Put"
        )
        
        assert call.is_put is False
        assert put.is_put is True

    def test_is_call_case_insensitive(self):
        """Test that option type comparison is case-insensitive."""
        contracts = [
            OptionContract(symbol="F", strike=10.0, expiration_date="2026-01-16", option_type="call"),
            OptionContract(symbol="F", strike=10.0, expiration_date="2026-01-16", option_type="CALL"),
            OptionContract(symbol="F", strike=10.0, expiration_date="2026-01-16", option_type="Call"),
        ]
        
        for contract in contracts:
            assert contract.is_call is True
            assert contract.is_put is False

    def test_bid_ask_spread_calculation(self):
        """Test bid-ask spread calculation."""
        contract = OptionContract(
            symbol="F",
            strike=10.0,
            expiration_date="2026-01-16",
            option_type="Call",
            bid=1.25,
            ask=1.30
        )
        
        assert abs(contract.bid_ask_spread - 0.05) < 0.001  # Use tolerance for float comparison

    def test_bid_ask_spread_missing_bid(self):
        """Test spread when bid is missing."""
        contract = OptionContract(
            symbol="F",
            strike=10.0,
            expiration_date="2026-01-16",
            option_type="Call",
            ask=1.30
        )
        
        assert contract.bid_ask_spread is None

    def test_bid_ask_spread_missing_ask(self):
        """Test spread when ask is missing."""
        contract = OptionContract(
            symbol="F",
            strike=10.0,
            expiration_date="2026-01-16",
            option_type="Call",
            bid=1.25
        )
        
        assert contract.bid_ask_spread is None

    def test_mid_price_calculation(self):
        """Test mid-price calculation."""
        contract = OptionContract(
            symbol="F",
            strike=10.0,
            expiration_date="2026-01-16",
            option_type="Call",
            bid=1.20,
            ask=1.30
        )
        
        assert contract.mid_price == 1.25

    def test_mid_price_missing_values(self):
        """Test mid-price when bid or ask is missing."""
        contract_no_bid = OptionContract(
            symbol="F",
            strike=10.0,
            expiration_date="2026-01-16",
            option_type="Call",
            ask=1.30
        )
        contract_no_ask = OptionContract(
            symbol="F",
            strike=10.0,
            expiration_date="2026-01-16",
            option_type="Call",
            bid=1.20
        )
        
        assert contract_no_bid.mid_price is None
        assert contract_no_ask.mid_price is None

    def test_to_dict(self):
        """Test conversion to dictionary."""
        contract = OptionContract(
            symbol="F",
            strike=10.0,
            expiration_date="2026-01-16",
            option_type="Call",
            bid=1.25,
            ask=1.30,
            last=1.27,
            volume=1500
        )
        
        data = contract.to_dict()
        
        assert isinstance(data, dict)
        assert data["symbol"] == "F"
        assert data["strike"] == 10.0
        assert data["expiration_date"] == "2026-01-16"
        assert data["option_type"] == "Call"
        assert data["bid"] == 1.25
        assert data["ask"] == 1.30
        assert data["last"] == 1.27
        assert data["volume"] == 1500

    def test_repr(self):
        """Test string representation."""
        contract = OptionContract(
            symbol="F",
            strike=10.0,
            expiration_date="2026-01-16",
            option_type="Call"
        )
        
        repr_str = repr(contract)
        
        assert "OptionContract" in repr_str
        assert "F" in repr_str
        assert "10.0" in repr_str
        assert "2026-01-16" in repr_str
        assert "Call" in repr_str


class TestOptionsChain:
    """Test suite for OptionsChain class."""

    @pytest.fixture
    def sample_contracts(self):
        """Create sample contracts for testing."""
        return [
            OptionContract(
                symbol="F",
                strike=10.0,
                expiration_date="2026-01-16",
                option_type="Call",
                bid=1.25,
                ask=1.30
            ),
            OptionContract(
                symbol="F",
                strike=10.0,
                expiration_date="2026-01-16",
                option_type="Put",
                bid=0.85,
                ask=0.90
            ),
            OptionContract(
                symbol="F",
                strike=11.0,
                expiration_date="2026-01-16",
                option_type="Call",
                bid=0.75,
                ask=0.80
            ),
            OptionContract(
                symbol="F",
                strike=10.0,
                expiration_date="2026-02-20",
                option_type="Call",
                bid=1.50,
                ask=1.55
            ),
        ]

    def test_options_chain_initialization(self, sample_contracts):
        """Test options chain initialization."""
        chain = OptionsChain(
            symbol="F",
            contracts=sample_contracts,
            retrieved_at="2026-01-13T12:00:00Z"
        )
        
        assert chain.symbol == "F"
        assert len(chain.contracts) == 4
        assert chain.retrieved_at == "2026-01-13T12:00:00Z"

    def test_get_calls(self, sample_contracts):
        """Test filtering for call options."""
        chain = OptionsChain(
            symbol="F",
            contracts=sample_contracts,
            retrieved_at="2026-01-13T12:00:00Z"
        )
        
        calls = chain.get_calls()
        
        assert len(calls) == 3
        assert all(c.is_call for c in calls)

    def test_get_puts(self, sample_contracts):
        """Test filtering for put options."""
        chain = OptionsChain(
            symbol="F",
            contracts=sample_contracts,
            retrieved_at="2026-01-13T12:00:00Z"
        )
        
        puts = chain.get_puts()
        
        assert len(puts) == 1
        assert all(c.is_put for c in puts)

    def test_get_by_expiration(self, sample_contracts):
        """Test filtering by expiration date."""
        chain = OptionsChain(
            symbol="F",
            contracts=sample_contracts,
            retrieved_at="2026-01-13T12:00:00Z"
        )
        
        jan_contracts = chain.get_by_expiration("2026-01-16")
        feb_contracts = chain.get_by_expiration("2026-02-20")
        
        assert len(jan_contracts) == 3
        assert len(feb_contracts) == 1
        assert all(c.expiration_date == "2026-01-16" for c in jan_contracts)
        assert all(c.expiration_date == "2026-02-20" for c in feb_contracts)

    def test_get_expirations(self, sample_contracts):
        """Test getting unique expirations."""
        chain = OptionsChain(
            symbol="F",
            contracts=sample_contracts,
            retrieved_at="2026-01-13T12:00:00Z"
        )
        
        expirations = chain.get_expirations()
        
        assert len(expirations) == 2
        assert expirations == ["2026-01-16", "2026-02-20"]  # Should be sorted

    def test_get_strikes(self, sample_contracts):
        """Test getting unique strikes."""
        chain = OptionsChain(
            symbol="F",
            contracts=sample_contracts,
            retrieved_at="2026-01-13T12:00:00Z"
        )
        
        strikes = chain.get_strikes()
        
        assert len(strikes) == 2
        assert strikes == [10.0, 11.0]  # Should be sorted

    def test_get_strikes_by_expiration(self, sample_contracts):
        """Test getting strikes for specific expiration."""
        chain = OptionsChain(
            symbol="F",
            contracts=sample_contracts,
            retrieved_at="2026-01-13T12:00:00Z"
        )
        
        jan_strikes = chain.get_strikes("2026-01-16")
        feb_strikes = chain.get_strikes("2026-02-20")
        
        assert jan_strikes == [10.0, 11.0]
        assert feb_strikes == [10.0]

    def test_to_dict(self, sample_contracts):
        """Test conversion to dictionary."""
        chain = OptionsChain(
            symbol="F",
            contracts=sample_contracts,
            retrieved_at="2026-01-13T12:00:00Z"
        )
        
        data = chain.to_dict()
        
        assert isinstance(data, dict)
        assert data["symbol"] == "F"
        assert data["retrieved_at"] == "2026-01-13T12:00:00Z"
        assert data["total_contracts"] == 4
        assert data["total_calls"] == 3
        assert data["total_puts"] == 1
        assert len(data["expirations"]) == 2
        assert len(data["contracts"]) == 4

    def test_repr(self, sample_contracts):
        """Test string representation."""
        chain = OptionsChain(
            symbol="F",
            contracts=sample_contracts,
            retrieved_at="2026-01-13T12:00:00Z"
        )
        
        repr_str = repr(chain)
        
        assert "OptionsChain" in repr_str
        assert "F" in repr_str
        assert "4 contracts" in repr_str
        assert "2 expirations" in repr_str

    def test_empty_chain(self):
        """Test chain with no contracts."""
        chain = OptionsChain(
            symbol="F",
            contracts=[],
            retrieved_at="2026-01-13T12:00:00Z"
        )
        
        assert len(chain.contracts) == 0
        assert len(chain.get_calls()) == 0
        assert len(chain.get_puts()) == 0
        assert len(chain.get_expirations()) == 0
        assert len(chain.get_strikes()) == 0
