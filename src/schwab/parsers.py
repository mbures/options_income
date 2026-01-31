"""
Schwab API response parsers.

This module provides functions for parsing Schwab API responses into internal
data models. These parsers are used by the SchwabClient to convert raw API
responses into structured objects.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List

from src.models.base import OptionContract, OptionsChain
from src.volatility_models import PriceData

from .models import SchwabAccount, SchwabAccountBalances, SchwabPosition

logger = logging.getLogger(__name__)


def parse_schwab_option_chain(
    symbol: str, data: Dict[str, Any]
) -> OptionsChain:
    """
    Parse Schwab options chain format to internal OptionsChain model.

    Args:
        symbol: Underlying symbol
        data: Raw Schwab API response

    Returns:
        OptionsChain object with contracts in internal format
    """
    contracts: List[OptionContract] = []

    # Parse call contracts
    call_exp_map = data.get("callExpDateMap", {})
    for exp_date_key, strikes in call_exp_map.items():
        # exp_date_key format: "2026-02-21:30" (expiration:daysToExpiration)
        exp_date = exp_date_key.split(":")[0]

        for strike_price, option_list in strikes.items():
            for option_data in option_list:
                contract = parse_schwab_contract(
                    symbol, exp_date, float(strike_price), "Call", option_data
                )
                contracts.append(contract)

    # Parse put contracts
    put_exp_map = data.get("putExpDateMap", {})
    for exp_date_key, strikes in put_exp_map.items():
        exp_date = exp_date_key.split(":")[0]

        for strike_price, option_list in strikes.items():
            for option_data in option_list:
                contract = parse_schwab_contract(
                    symbol, exp_date, float(strike_price), "Put", option_data
                )
                contracts.append(contract)

    return OptionsChain(
        symbol=symbol,
        contracts=contracts,
        retrieved_at=datetime.now().isoformat(),
    )


def parse_schwab_contract(
    symbol: str,
    expiration_date: str,
    strike: float,
    option_type: str,
    data: Dict[str, Any],
) -> OptionContract:
    """
    Parse a single Schwab option contract to internal format.

    Args:
        symbol: Underlying symbol
        expiration_date: Expiration date (YYYY-MM-DD)
        strike: Strike price
        option_type: "Call" or "Put"
        data: Schwab contract data

    Returns:
        OptionContract in internal format
    """
    return OptionContract(
        symbol=symbol,
        expiration_date=expiration_date,
        strike=strike,
        option_type=option_type,
        bid=data.get("bid", 0.0),
        ask=data.get("ask", 0.0),
        last=data.get("last", 0.0),
        volume=data.get("totalVolume", 0),
        open_interest=data.get("openInterest", 0),
        implied_volatility=data.get("volatility", 0.0) / 100.0,  # Schwab returns as percentage
        delta=data.get("delta", 0.0),
        gamma=data.get("gamma", 0.0),
        theta=data.get("theta", 0.0),
        vega=data.get("vega", 0.0),
    )


def parse_schwab_account(data: Dict[str, Any]) -> SchwabAccount:
    """
    Parse Schwab account data to internal SchwabAccount model.

    Args:
        data: Raw Schwab API account response

    Returns:
        SchwabAccount object
    """
    # Account data is nested under "securitiesAccount" key
    account_data = data.get("securitiesAccount", data)

    # Parse positions
    positions = []
    positions_data = account_data.get("positions", [])
    for position_data in positions_data:
        position = parse_schwab_position(position_data)
        positions.append(position)

    # Parse balances
    balances_data = account_data.get("currentBalances", {})
    balances = parse_schwab_balances(balances_data)

    return SchwabAccount(
        account_number=account_data.get("accountNumber", ""),
        account_type=account_data.get("type", ""),
        account_nickname=account_data.get("nickname"),
        positions=positions,
        balances=balances,
        is_closing_only=account_data.get("isClosingOnlyRestricted", False),
        is_day_trader=account_data.get("isDayTrader", False),
    )


def parse_schwab_position(data: Dict[str, Any]) -> SchwabPosition:
    """
    Parse a single Schwab position to internal format.

    Args:
        data: Schwab position data

    Returns:
        SchwabPosition object
    """
    instrument = data.get("instrument", {})
    symbol = instrument.get("symbol", "")
    asset_type = instrument.get("assetType", "")

    return SchwabPosition(
        symbol=symbol,
        quantity=data.get("longQuantity", 0.0) + data.get("shortQuantity", 0.0),
        average_price=data.get("averagePrice", 0.0),
        current_price=data.get("marketValue", 0.0) / max(data.get("longQuantity", 0.0) + data.get("shortQuantity", 0.0), 1),
        market_value=data.get("marketValue", 0.0),
        day_gain=data.get("currentDayProfitLoss", 0.0),
        day_gain_percent=data.get("currentDayProfitLossPercentage", 0.0),
        total_gain=data.get("marketValue", 0.0) - (data.get("averagePrice", 0.0) * (data.get("longQuantity", 0.0) + data.get("shortQuantity", 0.0))),
        total_gain_percent=None,  # Calculated separately if needed
        instrument_type=instrument.get("instrumentType", ""),
        asset_type=asset_type,
    )


def parse_schwab_balances(data: Dict[str, Any]) -> SchwabAccountBalances:
    """
    Parse Schwab account balance data to internal format.

    Args:
        data: Schwab balance data

    Returns:
        SchwabAccountBalances object
    """
    return SchwabAccountBalances(
        cash_balance=data.get("cashBalance", 0.0),
        cash_available_for_trading=data.get("cashAvailableForTrading", 0.0),
        cash_available_for_withdrawal=data.get("cashAvailableForWithdrawal", 0.0),
        market_value=data.get("liquidationValue", 0.0),
        total_cash=data.get("totalCash", 0.0),
        account_value=data.get("liquidationValue", 0.0),
        buying_power=data.get("buyingPower"),
    )


def parse_schwab_price_history(
    symbol: str, data: Dict[str, Any]
) -> PriceData:
    """
    Parse Schwab price history response to PriceData model.

    Schwab returns candles in format:
    {
        "candles": [
            {
                "open": 150.0,
                "high": 152.5,
                "low": 149.0,
                "close": 151.0,
                "volume": 1000000,
                "datetime": 1704067200000  # milliseconds since epoch
            },
            ...
        ],
        "symbol": "AAPL",
        "empty": false
    }

    Args:
        symbol: Stock symbol
        data: Raw Schwab API response

    Returns:
        PriceData object with parsed OHLCV data

    Raises:
        ValueError: If no price data returned
    """
    from .exceptions import SchwabAPIError

    candles = data.get("candles", [])

    if not candles:
        raise SchwabAPIError(f"No price data returned for {symbol}")

    # Parse candles into lists
    dates: List[str] = []
    opens: List[float] = []
    highs: List[float] = []
    lows: List[float] = []
    closes: List[float] = []
    volumes: List[int] = []

    for candle in candles:
        # Convert milliseconds timestamp to date string
        timestamp_ms = candle.get("datetime", 0)
        dt = datetime.fromtimestamp(timestamp_ms / 1000)
        dates.append(dt.strftime("%Y-%m-%d"))

        opens.append(float(candle.get("open", 0.0)))
        highs.append(float(candle.get("high", 0.0)))
        lows.append(float(candle.get("low", 0.0)))
        closes.append(float(candle.get("close", 0.0)))
        volumes.append(int(candle.get("volume", 0)))

    logger.debug(f"Parsed {len(candles)} candles for {symbol}")

    return PriceData(
        dates=dates,
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        volumes=volumes,
    )
