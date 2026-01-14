"""Service layer for options chain operations."""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from .models import OptionContract, OptionsChain
from .finnhub_client import FinnhubClient, FinnhubAPIError


logger = logging.getLogger(__name__)


class DataValidationError(Exception):
    """Exception raised for data validation errors."""

    pass


class OptionsChainService:
    """
    Service for retrieving and processing options chain data.

    This service:
    - Coordinates API client and data models
    - Validates API responses
    - Parses and transforms data
    - Handles business logic
    """

    def __init__(self, client: FinnhubClient):
        """
        Initialize service with Finnhub client.

        Args:
            client: FinnhubClient instance for API calls
        """
        self.client = client

    def get_options_chain(self, symbol: str) -> OptionsChain:
        """
        Retrieve and parse options chain for a symbol.

        Args:
            symbol: Stock ticker symbol

        Returns:
            OptionsChain object with parsed contracts

        Raises:
            FinnhubAPIError: If API call fails
            DataValidationError: If response is invalid
        """
        # Fetch raw data from API
        logger.info(f"Fetching options chain for {symbol}")
        raw_data = self.client.get_option_chain(symbol)

        # Validate response structure
        self._validate_response(raw_data)

        # Parse contracts
        contracts = self._parse_contracts(raw_data, symbol)

        # Log summary
        logger.info(
            f"Parsed {len(contracts)} contracts for {symbol} "
            f"({len([c for c in contracts if c.is_call])} calls, "
            f"{len([c for c in contracts if c.is_put])} puts)"
        )

        # Create options chain object
        return OptionsChain(
            symbol=symbol.upper(),
            contracts=contracts,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
        )

    def _validate_response(self, data: Dict[str, Any]) -> None:
        """
        Validate API response structure.

        Args:
            data: Raw API response

        Raises:
            DataValidationError: If response structure is invalid
        """
        if not isinstance(data, dict):
            raise DataValidationError(f"Response is not a dictionary, got {type(data)}")

        # Check if response has error
        if "error" in data:
            raise DataValidationError(f"API returned error: {data['error']}")

        # Finnhub may return empty response for invalid symbols
        if not data or (len(data) == 0):
            raise DataValidationError(
                "Empty response from API. Symbol may not have options available."
            )

    def _parse_contracts(self, raw_data: Dict[str, Any], symbol: str) -> List[OptionContract]:
        """
        Parse raw API response into OptionContract objects.

        Args:
            raw_data: Raw API response dictionary
            symbol: Stock ticker symbol

        Returns:
            List of parsed OptionContract objects

        Raises:
            DataValidationError: If no valid contracts found
        """
        contracts: List[OptionContract] = []

        # Try different response structures
        # Structure 1: {"data": [contracts]}
        # Structure 2: Direct list [contracts]
        if isinstance(raw_data, list):
            data_list = raw_data
        else:
            data_list = raw_data.get("data", [])

            # Structure 3: Try to extract contracts from other possible structures
            if not data_list:
                data_list = self._extract_contracts_from_response(raw_data)

        if not data_list:
            raise DataValidationError(
                "No contract data found in response. " "API response structure may have changed."
            )

        # Parse each contract
        parse_errors = 0
        for item in data_list:
            try:
                contract = self._parse_single_contract(item, symbol)
                contracts.append(contract)
            except Exception as e:
                parse_errors += 1
                logger.warning(f"Failed to parse contract: {e}. Data: {item}")

        if parse_errors > 0:
            logger.warning(f"Failed to parse {parse_errors} out of {len(data_list)} contracts")

        if not contracts:
            raise DataValidationError("No valid contracts found. All contract parsing failed.")

        return contracts

    def _parse_single_contract(self, data: Dict[str, Any], symbol: str) -> OptionContract:
        """
        Parse a single contract from API data.

        Args:
            data: Contract data dictionary
            symbol: Stock ticker symbol

        Returns:
            Parsed OptionContract object

        Raises:
            KeyError: If required fields are missing
            ValueError: If data types are invalid
        """
        # Required fields
        strike = float(data["strike"])
        expiration_date = str(data["expirationDate"])
        option_type = str(data["type"])

        # Validate option type
        if option_type.lower() not in ["call", "put"]:
            raise ValueError(f"Invalid option type: {option_type}")

        return OptionContract(
            symbol=symbol,
            strike=strike,
            expiration_date=expiration_date,
            option_type=option_type,
            bid=self._safe_float(data.get("bid")),
            ask=self._safe_float(data.get("ask")),
            last=self._safe_float(data.get("last")),
            volume=self._safe_int(data.get("volume")),
            open_interest=self._safe_int(data.get("openInterest")),
            delta=self._safe_float(data.get("delta")),
            gamma=self._safe_float(data.get("gamma")),
            theta=self._safe_float(data.get("theta")),
            vega=self._safe_float(data.get("vega")),
            rho=self._safe_float(data.get("rho")),
            implied_volatility=self._safe_float(data.get("impliedVolatility")),
        )

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        """
        Safely convert value to float.

        Args:
            value: Value to convert

        Returns:
            Float value or None if conversion fails
        """
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            logger.debug(f"Could not convert {value} to float")
            return None

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        """
        Safely convert value to int.

        Args:
            value: Value to convert

        Returns:
            Integer value or None if conversion fails
        """
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            logger.debug(f"Could not convert {value} to int")
            return None

    def _extract_contracts_from_response(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract contracts from alternate response structures.

        This handles different possible API response formats.

        Args:
            data: API response dictionary

        Returns:
            List of contract dictionaries
        """
        # Try common alternate structures
        contracts = []

        # Check for nested structures
        for key in ["options", "contracts", "chain"]:
            if key in data:
                value = data[key]
                if isinstance(value, list):
                    contracts.extend(value)
                elif isinstance(value, dict):
                    # Might be grouped by expiration
                    for sub_value in value.values():
                        if isinstance(sub_value, list):
                            contracts.extend(sub_value)

        return contracts
