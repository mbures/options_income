# Finnhub Options Chain Data Retrieval System

A Python-based application for retrieving options chain data from the Finnhub API. This system provides a clean, type-safe interface for fetching and analyzing options contracts for equity securities.

## 📋 Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Architecture](#architecture)
- [Testing](#testing)
- [Development](#development)
- [Known Limitations](#known-limitations)
- [License](#license)

## ✨ Features

- ✅ **Robust API Integration**: Connect to Finnhub API with automatic retry logic and exponential backoff
- ✅ **Type-Safe Data Models**: Comprehensive type hints and validation for all data structures
- ✅ **Multiple Output Formats**: JSON, summary, and minimal output formats
- ✅ **Comprehensive Error Handling**: Clear error messages with actionable guidance
- ✅ **Extensive Test Coverage**: 76 unit tests with >98% coverage for core modules
- ✅ **Code Quality**: Linted and formatted with ruff, type-checked with mypy
- ✅ **Well-Documented**: Inline docstrings, type hints, and comprehensive README

## 📦 Requirements

- **Python**: 3.9 or higher
- **Finnhub API Key**: Free API key from [https://finnhub.io/register](https://finnhub.io/register)

### Dependencies

```
requests>=2.31.0
python-dotenv>=1.0.0
```

## 🚀 Installation

### 1. Clone or Download the Repository

```bash
cd finnhub-options
```

### 2. Create Virtual Environment (Recommended)

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

For development (includes testing and linting tools):

```bash
pip install -r requirements-dev.txt
```

## ⚙️ Configuration

### Set API Key

Get a free API key from [Finnhub](https://finnhub.io/register) and set it as an environment variable:

**Linux/Mac:**
```bash
export FINNHUB_API_KEY="your_api_key_here"
```

**Windows (Command Prompt):**
```cmd
set FINNHUB_API_KEY=your_api_key_here
```

**Windows (PowerShell):**
```powershell
$env:FINNHUB_API_KEY="your_api_key_here"
```

### Alternative: Use .env File

Create a `.env` file in the project root:

```
FINNHUB_API_KEY=your_api_key_here
```

## 📖 Usage

### Basic Usage

Fetch options chain for Ford (ticker: F):

```bash
python -m src.main F
```

### Output Formats

**JSON Format (Default):**
```bash
python -m src.main F
```

**Human-Readable Summary:**
```bash
python -m src.main F --output summary
```

**Minimal Output:**
```bash
python -m src.main F --output minimal
```

### Save to File

```bash
python -m src.main F --output-file ford_options.json
```

### Enable Verbose Logging

```bash
python -m src.main F --verbose
```

### Examples

```bash
# Get options for Apple
python -m src.main AAPL

# Get Tesla options with summary output
python -m src.main TSLA --output summary

# Get Microsoft options and save to file
python -m src.main MSFT --output-file msft_options.json

# Get NVIDIA options with verbose logging
python -m src.main NVDA --verbose
```

### Sample Output

**Summary Format:**
```
======================================================================
Options Chain for F
======================================================================
Retrieved at: 2026-01-13T15:30:00+00:00
Total contracts: 248
  Calls: 124
  Puts: 124
Expirations: 8

Available Expirations:
  2026-01-16: 32 contracts
  2026-02-20: 28 contracts
  2026-03-20: 30 contracts
  ... and 5 more

Sample Call Options:
  Expiration    Strike      Bid      Ask     Last   Volume
  ------------------------------------------------------------
  2026-01-16   $ 10.00  $  1.25  $  1.30  $  1.27     1500
  2026-01-16   $ 11.00  $  0.75  $  0.80  $  0.77      850
  ...

Sample Put Options:
  Expiration    Strike      Bid      Ask     Last   Volume
  ------------------------------------------------------------
  2026-01-16   $ 10.00  $  0.85  $  0.90  $  0.87     1200
  2026-01-16   $  9.00  $  0.45  $  0.50  $  0.47      650
  ...
======================================================================
Note: Finnhub options data may have accuracy limitations. Verify before trading.
======================================================================
```

**JSON Format (excerpt):**
```json
{
  "symbol": "F",
  "retrieved_at": "2026-01-13T15:30:00+00:00",
  "total_contracts": 248,
  "total_calls": 124,
  "total_puts": 124,
  "expirations": ["2026-01-16", "2026-02-20", ...],
  "contracts": [
    {
      "symbol": "F",
      "strike": 10.0,
      "expiration_date": "2026-01-16",
      "option_type": "Call",
      "bid": 1.25,
      "ask": 1.30,
      "last": 1.27,
      "volume": 1500,
      "open_interest": 5000,
      "delta": 0.55,
      "gamma": 0.08,
      ...
    }
  ]
}
```

## 🏗️ Architecture

### Project Structure

```
finnhub-options/
├── src/
│   ├── __init__.py
│   ├── config.py           # Configuration management
│   ├── models.py           # Data models (OptionContract, OptionsChain)
│   ├── finnhub_client.py   # HTTP client for Finnhub API
│   ├── options_service.py  # Business logic layer
│   └── main.py            # CLI application entry point
├── tests/
│   ├── test_config.py
│   ├── test_models.py
│   ├── test_finnhub_client.py
│   └── test_options_service.py
├── requirements.txt
├── requirements-dev.txt
├── pytest.ini
├── pyproject.toml          # Contains ruff configuration
└── README.md
```

### Module Overview

**`config.py`**: Configuration management
- Loads API key from environment variables
- Validates configuration
- Provides configuration objects to other modules

**`models.py`**: Data models
- `OptionContract`: Represents a single option contract
- `OptionsChain`: Represents a complete options chain for a ticker
- Helper methods for filtering and analysis

**`finnhub_client.py`**: API client
- HTTP communication with Finnhub API
- Retry logic with exponential backoff
- Error handling and logging

**`options_service.py`**: Service layer
- Business logic for options chain operations
- Coordinates API client and data models
- Data validation and parsing

**`main.py`**: CLI application
- Command-line argument parsing
- Output formatting
- Top-level error handling

### Design Principles

- **Separation of Concerns**: Clear boundaries between layers
- **Type Safety**: Comprehensive type hints throughout
- **Testability**: Dependency injection and interfaces for easy mocking
- **Error Handling**: Explicit error types and graceful degradation
- **Documentation**: Inline docs, type hints, and comprehensive README

## 🧪 Testing

### Run All Tests

```bash
pytest
```

### Run with Coverage Report

```bash
pytest --cov=src --cov-report=html
```

View coverage report: `open htmlcov/index.html`

### Run Specific Test File

```bash
pytest tests/test_models.py
```

### Run with Verbose Output

```bash
pytest -v
```

### Test Coverage

Current test coverage:

```
Name                     Stmts   Miss  Cover
--------------------------------------------
src/config.py               25      0   100%
src/finnhub_client.py       63      1    98%
src/models.py               61      0   100%
src/options_service.py      84      2    98%
--------------------------------------------
TOTAL                      233      3    99%
```

## 🛠️ Development

### Code Formatting and Linting

This project uses **ruff** for both linting and formatting (configured in `pyproject.toml`).

```bash
# Check for linting issues
ruff check .

# Auto-fix linting issues
ruff check . --fix

# Check formatting
ruff format --check .

# Apply formatting
ruff format .
```

### Type Checking

```bash
mypy src/
```

### Run All Quality Checks

```bash
# Lint and auto-fix
ruff check . --fix

# Format code
ruff format .

# Type check
mypy src/

# Run tests with coverage
pytest --cov=src
```

### Adding New Features

1. Write tests first (TDD approach)
2. Implement feature
3. Run tests: `pytest`
4. Lint and format code: `ruff check . --fix && ruff format .`
5. Type check: `mypy src/`
6. Update documentation

## ⚠️ Known Limitations

### Finnhub API Limitations

Based on [GitHub Issue #545](https://github.com/finnhubio/Finnhub-API/issues/545), the Finnhub options data has some known accuracy issues:

1. **Stale Pricing**: Bid/ask prices may be outdated, especially for at-the-money options
2. **Data Discrepancies**: Prices may differ significantly from live market data (>80% in some cases)
3. **Greeks Reliability**: Greeks and contract metadata are generally more reliable than pricing
4. **Not for Trading**: Data should be verified against other sources before making trading decisions

### Rate Limits

- **Free Tier**: 60 API calls per minute, 30 calls per second
- Requests are automatically retried with exponential backoff
- Rate limit errors (HTTP 429) are clearly reported

### Data Availability

- Not all ticker symbols have options available
- Some symbols may return empty data
- Historical options data may be limited

## 📚 API Reference

### OptionContract

Represents a single option contract.

**Attributes:**
- `symbol`: str - Stock ticker symbol
- `strike`: float - Strike price
- `expiration_date`: str - Expiration date (YYYY-MM-DD)
- `option_type`: str - "Call" or "Put"
- `bid`: Optional[float] - Bid price
- `ask`: Optional[float] - Ask price
- `last`: Optional[float] - Last traded price
- `volume`: Optional[int] - Trading volume
- `open_interest`: Optional[int] - Open interest
- `delta`: Optional[float] - Delta (Greek)
- `gamma`: Optional[float] - Gamma (Greek)
- `theta`: Optional[float] - Theta (Greek)
- `vega`: Optional[float] - Vega (Greek)
- `rho`: Optional[float] - Rho (Greek)
- `implied_volatility`: Optional[float] - Implied volatility

**Properties:**
- `bid_ask_spread`: Calculated spread between ask and bid
- `mid_price`: Mid-point between bid and ask
- `is_call`: Boolean indicating if contract is a call
- `is_put`: Boolean indicating if contract is a put

### OptionsChain

Represents a complete options chain for a ticker.

**Attributes:**
- `symbol`: str - Stock ticker symbol
- `contracts`: List[OptionContract] - List of all contracts
- `retrieved_at`: str - ISO timestamp of retrieval

**Methods:**
- `get_calls()`: Get all call options
- `get_puts()`: Get all put options
- `get_by_expiration(date)`: Get contracts for specific expiration
- `get_expirations()`: Get unique expiration dates
- `get_strikes(expiration)`: Get unique strike prices

## 🤝 Contributing

This is a demonstration project. For production use, consider:

1. Adding data caching layer
2. Supporting multiple data providers
3. Implementing options analytics (Greeks calculation, probability analysis)
4. Adding database integration for historical storage
5. Creating web API or dashboard interface

## 📄 License

This project is provided as-is for educational and demonstration purposes.

## 🙏 Acknowledgments

- **Finnhub.io**: For providing the options data API
- **Product Requirements**: Defined by the Stock Quant persona
- **System Design**: Architected by the Software Developer persona

## 📞 Support

For issues related to:

- **Finnhub API**: Visit [Finnhub Documentation](https://finnhub.io/docs/api)
- **API Key**: Get your free key at [Finnhub Register](https://finnhub.io/register)
- **Known Issues**: See GitHub Issue #545 for options data accuracy concerns

---

**⚠️ Disclaimer**: This tool is for informational purposes only. Options trading involves significant risk. Always verify data with multiple sources before making trading decisions. Not intended as financial advice.

---

**Created**: January 13, 2026  
**Version**: 1.0.0  
**Python**: 3.9+
