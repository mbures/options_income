"""Service layer for options chain operations."""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from .finnhub_client import FinnhubClient
from .models import OptionContract, OptionsChain

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

    def _validate_response(self, data: dict[str, Any]) -> None:
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

    def _parse_contracts(self, raw_data: dict[str, Any], symbol: str) -> list[OptionContract]:
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
        contracts: list[OptionContract] = []

        # Try different response structures
        # Structure 1: {"data": [expiration_groups]} where each group has "options": {"CALL": [], "PUT": []}
        # Structure 2: Direct list [contracts]
        # Structure 3: Other nested structures

        if isinstance(raw_data, list):
            # Could be a list of expiration groups OR a list of contracts
            data_list = raw_data
        else:
            data_list = raw_data.get("data", [])

        # If we got data, try to extract contracts from it
        if data_list:
            contracts = self._extract_contracts_from_list(data_list, symbol)
        else:
            # Try alternate extraction methods
            extracted = self._extract_contracts_from_response(raw_data)
            if extracted:
                contracts = self._parse_contracts_from_list(extracted, symbol)

        if not contracts:
            raise DataValidationError(
                "No contract data found in response. API response structure may have changed."
            )

        return contracts

    def _extract_contracts_from_list(
        self, data_list: list[Any], symbol: str
    ) -> list[OptionContract]:
        """
        Extract and parse contracts from a list of items.

        The list might contain:
        1. Expiration groups (dicts with "options" key)
        2. Direct contract objects

        Args:
            data_list: List of data items
            symbol: Stock ticker symbol

        Returns:
            List of parsed OptionContract objects
        """
        contracts: list[OptionContract] = []
        parse_errors = 0
        total_items = 0

        for item in data_list:
            if not isinstance(item, dict):
                continue

            # Check if this is an expiration group (has "options" key with CALL/PUT structure)
            if "options" in item and isinstance(item["options"], dict):
                # Extract contracts from the nested structure
                for option_type in ["CALL", "PUT"]:
                    if option_type in item["options"]:
                        option_contracts = item["options"][option_type]
                        if isinstance(option_contracts, list):
                            for contract_data in option_contracts:
                                total_items += 1
                                try:
                                    contract = self._parse_single_contract(contract_data, symbol)
                                    contracts.append(contract)
                                except Exception as e:
                                    parse_errors += 1
                                    if parse_errors <= 3:  # Only log first few errors to avoid spam
                                        logger.debug(f"Failed to parse contract: {e}")
            else:
                # Try to parse as a direct contract
                total_items += 1
                try:
                    contract = self._parse_single_contract(item, symbol)
                    contracts.append(contract)
                except Exception as e:
                    parse_errors += 1
                    if parse_errors <= 3:
                        logger.debug(f"Failed to parse contract: {e}")

        if parse_errors > 0:
            logger.info(
                f"Parsed {len(contracts)} contracts, {parse_errors} errors out of {total_items} items"
            )

        if not contracts and total_items > 0:
            raise DataValidationError("No valid contracts found. All contract parsing failed.")

        return contracts

    def _parse_contracts_from_list(
        self, data_list: list[dict[str, Any]], symbol: str
    ) -> list[OptionContract]:
        """Parse a list of contract dictionaries."""
        contracts: list[OptionContract] = []
        parse_errors = 0

        for item in data_list:
            try:
                contract = self._parse_single_contract(item, symbol)
                contracts.append(contract)
            except Exception as e:
                parse_errors += 1
                if parse_errors <= 3:
                    logger.debug(f"Failed to parse contract: {e}")

        if parse_errors > 0:
            logger.info(f"Parsed {len(contracts)} contracts, {parse_errors} errors")

        return contracts

    def _parse_single_contract(self, data: dict[str, Any], symbol: str) -> OptionContract:
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

        # Handle both old and new API field names
        # Old API: "last", New API: "lastPrice"
        last_price = self._safe_float(data.get("lastPrice") or data.get("last"))

        return OptionContract(
            symbol=symbol,
            strike=strike,
            expiration_date=expiration_date,
            option_type=option_type,
            bid=self._safe_float(data.get("bid")),
            ask=self._safe_float(data.get("ask")),
            last=last_price,
            volume=self._safe_int(data.get("volume")),
            open_interest=self._safe_int(data.get("openInterest")),
            delta=self._safe_float(data.get("delta")),
            gamma=self._safe_float(data.get("gamma")),
            theta=self._safe_float(data.get("theta")),
            vega=self._safe_float(data.get("vega")),
            rho=self._safe_float(data.get("rho")),
            implied_volatility=self._normalize_iv(data.get("impliedVolatility")),
        )

    def _normalize_iv(self, value: Any) -> Optional[float]:
        """
        Normalize implied volatility to decimal form.

        Finnhub returns IV as a percentage (e.g., 26.93 means 26.93%).
        This method converts to decimal form (0.2693) for internal calculations.

        Args:
            value: Raw IV value from API

        Returns:
            IV as decimal (e.g., 0.2693), or None if invalid
        """
        raw_iv = self._safe_float(value)
        if raw_iv is None:
            return None
        # Convert from percentage to decimal
        return raw_iv / 100

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

    def _extract_contracts_from_response(self, data: dict[str, Any]) -> list[dict[str, Any]]:
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
                    # Direct list of contracts
                    contracts.extend(value)
                elif isinstance(value, dict):
                    # Might be grouped by type (CALL/PUT) or expiration
                    for _sub_key, sub_value in value.items():
                        if isinstance(sub_value, list):
                            # Found a list of contracts
                            contracts.extend(sub_value)
                        elif isinstance(sub_value, dict):
                            # Nested dict - recurse one more level
                            for nested_value in sub_value.values():
                                if isinstance(nested_value, list):
                                    contracts.extend(nested_value)

        return contracts
