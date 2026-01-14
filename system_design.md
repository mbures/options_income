# System Design Document
## Finnhub Options Chain Data Retrieval System

**Version:** 1.0  
**Date:** January 13, 2026  
**Author:** Software Developer  
**Status:** Draft

---

## 1. System Overview

### 1.1 Purpose

This document describes the technical architecture, design decisions, and implementation details for a Python-based system that retrieves options chain data from the Finnhub API. The system is designed to be modular, testable, and extensible for future enhancements.

### 1.2 Scope

The system includes:
- HTTP client for Finnhub API interaction
- Data models for options chain representation
- Configuration management
- Error handling and logging
- Data validation and parsing
- Unit tests and integration tests
- Command-line interface

### 1.3 Design Principles

- **Separation of Concerns**: API client, data models, and business logic are separated
- **Type Safety**: Comprehensive type hints throughout codebase
- **Testability**: Dependency injection and interfaces for easy mocking
- **Error Handling**: Explicit error types and graceful degradation
- **Documentation**: Inline docs, type hints, and comprehensive README
- **Code Quality**: Linting with pylint/black, type checking with mypy

---

## 2. Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Command Line Interface                   │
│                     (main.py, CLI args)                     │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    Application Layer                         │
│              (Orchestration, validation)                    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                  Service Layer                               │
│         (OptionsChainService, business logic)               │
└──────┬──────────────────────────────────────────────────┬───┘
       │                                                   │
       ▼                                                   ▼
┌──────────────────┐                         ┌──────────────────────┐
│   API Client     │                         │    Data Models       │
│  (FinnhubClient) │                         │  (OptionContract,    │
│                  │                         │   OptionsChain)      │
└──────┬───────────┘                         └──────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│              External API (Finnhub REST API)                  │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Component Diagram

```
┌─────────────────┐
│   config.py     │  ← Environment variables, constants
└─────────────────┘
         │
         ▼
┌─────────────────┐
│   models.py     │  ← Data classes for options
└─────────────────┘
         │
         ▼
┌─────────────────┐
│ finnhub_client.py│ ← HTTP client, API calls
└─────────────────┘
         │
         ▼
┌─────────────────┐
│ options_service.py│ ← Business logic, validation
└─────────────────┘
         │
         ▼
┌─────────────────┐
│    main.py      │  ← CLI entry point
└─────────────────┘
```

---

## 3. Module Design

### 3.1 Configuration Module (`config.py`)

**Purpose**: Centralize configuration management and constants.

**Responsibilities**:
- Load environment variables
- Define API endpoints and constants
- Validate configuration on startup
- Provide configuration access to other modules

**Key Components**:

```python
@dataclass
class FinnhubConfig:
    """Finnhub API configuration."""
    api_key: str
    base_url: str = "https://finnhub.io/api/v1"
    timeout: int = 10
    max_retries: int = 3
    retry_delay: float = 1.0

    @classmethod
    def from_env(cls) -> "FinnhubConfig":
        """Load configuration from environment variables."""
        api_key = os.getenv("FINNHUB_API_KEY")
        if not api_key:
            raise ValueError("FINNHUB_API_KEY environment variable not set")
        return cls(api_key=api_key)
```

**Design Decisions**:
- Use `dataclass` for type safety and validation
- Environment variables preferred over config files for security
- Sensible defaults for timeout and retry parameters
- Raise exception early if configuration is invalid

---

### 3.2 Data Models Module (`models.py`)

**Purpose**: Define type-safe data structures for options data.

**Responsibilities**:
- Model individual option contracts
- Model complete options chain
- Provide data validation
- Support serialization to JSON

**Key Components**:

```python
@dataclass
class OptionContract:
    """Represents a single option contract."""
    symbol: str
    strike: float
    expiration_date: str
    option_type: str  # "Call" or "Put"
    bid: Optional[float]
    ask: Optional[float]
    last: Optional[float]
    volume: Optional[int]
    open_interest: Optional[int]
    delta: Optional[float]
    gamma: Optional[float]
    theta: Optional[float]
    vega: Optional[float]
    rho: Optional[float]
    implied_volatility: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @property
    def bid_ask_spread(self) -> Optional[float]:
        """Calculate bid-ask spread."""
        if self.bid is not None and self.ask is not None:
            return self.ask - self.bid
        return None

    @property
    def is_call(self) -> bool:
        """Check if this is a call option."""
        return self.option_type.lower() == "call"

    @property
    def is_put(self) -> bool:
        """Check if this is a put option."""
        return self.option_type.lower() == "put"


@dataclass
class OptionsChain:
    """Represents a complete options chain for a ticker."""
    symbol: str
    contracts: List[OptionContract]
    retrieved_at: str

    def get_calls(self) -> List[OptionContract]:
        """Get all call options."""
        return [c for c in self.contracts if c.is_call]

    def get_puts(self) -> List[OptionContract]:
        """Get all put options."""
        return [c for c in self.contracts if c.is_put]

    def get_by_expiration(self, date: str) -> List[OptionContract]:
        """Get all contracts for a specific expiration date."""
        return [c for c in self.contracts if c.expiration_date == date]

    def get_expirations(self) -> List[str]:
        """Get unique expiration dates sorted chronologically."""
        return sorted(list(set(c.expiration_date for c in self.contracts)))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "symbol": self.symbol,
            "retrieved_at": self.retrieved_at,
            "total_contracts": len(self.contracts),
            "expirations": self.get_expirations(),
            "contracts": [c.to_dict() for c in self.contracts]
        }
```

**Design Decisions**:
- Use `dataclass` for automatic `__init__`, `__repr__`, etc.
- All pricing/volume fields are Optional (may be missing from API)
- Derived properties for common queries (is_call, bid_ask_spread)
- Helper methods for filtering (get_calls, get_puts, get_by_expiration)
- Serialization support for JSON output

---

### 3.3 API Client Module (`finnhub_client.py`)

**Purpose**: Handle all HTTP communication with Finnhub API.

**Responsibilities**:
- Construct API requests with proper authentication
- Handle HTTP errors and retries
- Parse API responses
- Implement rate limiting
- Provide clean interface to rest of application

**Key Components**:

```python
class FinnhubClient:
    """Client for interacting with Finnhub API."""

    def __init__(self, config: FinnhubConfig):
        """Initialize client with configuration."""
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "FinnhubOptionsClient/1.0"
        })

    def get_option_chain(self, symbol: str) -> Dict[str, Any]:
        """
        Retrieve options chain for a given symbol.
        
        Args:
            symbol: Stock ticker symbol (e.g., "F")
            
        Returns:
            API response as dictionary
            
        Raises:
            FinnhubAPIError: If API request fails
            ValueError: If symbol is invalid
        """
        if not symbol or not isinstance(symbol, str):
            raise ValueError(f"Invalid symbol: {symbol}")

        url = f"{self.config.base_url}/stock/option-chain"
        params = {
            "symbol": symbol.upper(),
            "token": self.config.api_key
        }

        try:
            response = self._make_request_with_retry(url, params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout as e:
            raise FinnhubAPIError(f"Request timeout for symbol {symbol}") from e
        except requests.exceptions.RequestException as e:
            raise FinnhubAPIError(f"API request failed: {str(e)}") from e

    def _make_request_with_retry(
        self,
        url: str,
        params: Dict[str, str],
        attempt: int = 1
    ) -> requests.Response:
        """Make HTTP request with exponential backoff retry."""
        try:
            response = self.session.get(
                url,
                params=params,
                timeout=self.config.timeout
            )
            return response
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            if attempt >= self.config.max_retries:
                raise
            
            delay = self.config.retry_delay * (2 ** (attempt - 1))
            logging.warning(
                f"Request failed (attempt {attempt}/{self.config.max_retries}). "
                f"Retrying in {delay}s..."
            )
            time.sleep(delay)
            return self._make_request_with_retry(url, params, attempt + 1)

    def close(self):
        """Close the HTTP session."""
        self.session.close()


class FinnhubAPIError(Exception):
    """Custom exception for Finnhub API errors."""
    pass
```

**Design Decisions**:
- Separate class for clean interface and testability
- Use `requests.Session` for connection pooling
- Exponential backoff for retry logic
- Custom exception type for API errors
- Type hints for all parameters and return values
- Context manager support (via close method)

---

### 3.4 Service Layer (`options_service.py`)

**Purpose**: Business logic for options chain operations.

**Responsibilities**:
- Coordinate between API client and data models
- Validate and parse API responses
- Handle data transformation
- Implement business rules
- Provide high-level interface for application

**Key Components**:

```python
class OptionsChainService:
    """Service for retrieving and processing options chain data."""

    def __init__(self, client: FinnhubClient):
        """Initialize service with Finnhub client."""
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
        raw_data = self.client.get_option_chain(symbol)
        
        # Validate response structure
        self._validate_response(raw_data)
        
        # Parse contracts
        contracts = self._parse_contracts(raw_data, symbol)
        
        # Create options chain object
        return OptionsChain(
            symbol=symbol.upper(),
            contracts=contracts,
            retrieved_at=datetime.now(timezone.utc).isoformat()
        )

    def _validate_response(self, data: Dict[str, Any]) -> None:
        """Validate API response structure."""
        if not isinstance(data, dict):
            raise DataValidationError("Response is not a dictionary")
        
        if "data" not in data and not isinstance(data.get("data"), list):
            # Some APIs return contracts directly in root
            # Check if data looks like it has contract fields
            if not self._looks_like_contracts(data):
                raise DataValidationError("Response missing 'data' field or valid contracts")

    def _looks_like_contracts(self, data: Dict[str, Any]) -> bool:
        """Check if data structure looks like it contains contracts."""
        # Implementation depends on actual API response format
        # This is a placeholder for actual validation logic
        return isinstance(data, dict) and len(data) > 0

    def _parse_contracts(
        self,
        raw_data: Dict[str, Any],
        symbol: str
    ) -> List[OptionContract]:
        """Parse raw API response into OptionContract objects."""
        contracts = []
        
        # Handle different possible response structures
        data_list = raw_data.get("data", [])
        if not data_list and isinstance(raw_data, dict):
            # API might return contracts in different structure
            data_list = self._extract_contracts_from_response(raw_data)

        for item in data_list:
            try:
                contract = self._parse_single_contract(item, symbol)
                contracts.append(contract)
            except Exception as e:
                logging.warning(f"Failed to parse contract: {e}")
                continue

        return contracts

    def _parse_single_contract(
        self,
        data: Dict[str, Any],
        symbol: str
    ) -> OptionContract:
        """Parse a single contract from API data."""
        return OptionContract(
            symbol=symbol,
            strike=float(data["strike"]),
            expiration_date=str(data["expirationDate"]),
            option_type=str(data["type"]),
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
            implied_volatility=self._safe_float(data.get("impliedVolatility"))
        )

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        """Safely convert value to float."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        """Safely convert value to int."""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    def _extract_contracts_from_response(
        self,
        data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Extract contracts from alternate response structures."""
        # Handle case where API returns contracts in different structure
        # This is a placeholder for handling different API response formats
        return []


class DataValidationError(Exception):
    """Exception raised for data validation errors."""
    pass
```

**Design Decisions**:
- Service layer separates business logic from API client
- Defensive parsing with try/except and safe conversion functions
- Logging for non-fatal errors (individual contract parse failures)
- Custom exception for validation errors
- Timestamp added to options chain for data freshness tracking

---

### 3.5 Main Application (`main.py`)

**Purpose**: Command-line interface and application entry point.

**Responsibilities**:
- Parse command-line arguments
- Initialize components
- Orchestrate service calls
- Format and display output
- Handle top-level errors

**Key Components**:

```python
def main():
    """Main entry point for the application."""
    parser = argparse.ArgumentParser(
        description="Retrieve options chain data from Finnhub API"
    )
    parser.add_argument(
        "symbol",
        type=str,
        help="Stock ticker symbol (e.g., F)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="json",
        choices=["json", "summary"],
        help="Output format (default: json)"
    )
    parser.add_argument(
        "--output-file",
        type=str,
        help="Save output to file instead of stdout"
    )

    args = parser.parse_args()

    try:
        # Load configuration
        config = FinnhubConfig.from_env()

        # Initialize client and service
        client = FinnhubClient(config)
        service = OptionsChainService(client)

        # Retrieve options chain
        options_chain = service.get_options_chain(args.symbol)

        # Format output
        if args.output == "json":
            output = json.dumps(options_chain.to_dict(), indent=2)
        else:
            output = format_summary(options_chain)

        # Write output
        if args.output_file:
            with open(args.output_file, "w") as f:
                f.write(output)
            print(f"Output written to {args.output_file}")
        else:
            print(output)

        # Cleanup
        client.close()

    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)
    except FinnhubAPIError as e:
        print(f"API error: {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(3)


def format_summary(options_chain: OptionsChain) -> str:
    """Format options chain as human-readable summary."""
    lines = [
        f"Options Chain for {options_chain.symbol}",
        f"Retrieved at: {options_chain.retrieved_at}",
        f"Total contracts: {len(options_chain.contracts)}",
        f"Expirations: {', '.join(options_chain.get_expirations()[:5])}...",
        "",
        "Sample Contracts:",
        ""
    ]

    # Show first 5 calls and puts
    calls = options_chain.get_calls()[:5]
    puts = options_chain.get_puts()[:5]

    lines.append("CALLS:")
    for contract in calls:
        lines.append(
            f"  {contract.expiration_date} ${contract.strike} "
            f"Bid: ${contract.bid} Ask: ${contract.ask}"
        )

    lines.append("")
    lines.append("PUTS:")
    for contract in puts:
        lines.append(
            f"  {contract.expiration_date} ${contract.strike} "
            f"Bid: ${contract.bid} Ask: ${contract.ask}"
        )

    return "\n".join(lines)
```

**Design Decisions**:
- Use argparse for CLI argument parsing
- Multiple output formats (JSON, summary)
- File output support
- Proper exit codes for different error types
- Clean resource cleanup (close client)

---

## 4. Error Handling Strategy

### 4.1 Error Categories

1. **Configuration Errors**: Missing API key, invalid config
2. **Network Errors**: Timeouts, connection failures
3. **API Errors**: Rate limiting, invalid requests, server errors
4. **Data Validation Errors**: Malformed responses, missing required fields
5. **Runtime Errors**: Unexpected exceptions

### 4.2 Error Handling Approach

```python
# Custom exception hierarchy
class FinnhubError(Exception):
    """Base exception for Finnhub-related errors."""
    pass

class FinnhubAPIError(FinnhubError):
    """API request failures."""
    pass

class DataValidationError(FinnhubError):
    """Data validation failures."""
    pass

class ConfigurationError(FinnhubError):
    """Configuration errors."""
    pass
```

### 4.3 Retry Logic

- **Transient errors** (timeouts, 503): Exponential backoff, max 3 retries
- **Client errors** (400, 401, 403): No retry, immediate failure
- **Rate limit** (429): Respect Retry-After header if present

---

## 5. Testing Strategy

### 5.1 Unit Tests

**Test Files**:
- `test_config.py`: Configuration loading and validation
- `test_models.py`: Data model methods and properties
- `test_finnhub_client.py`: API client with mocked responses
- `test_options_service.py`: Service layer logic

**Test Coverage Goals**:
- Configuration: 100%
- Models: 100%
- API Client: >90%
- Service: >85%
- Overall: >80%

**Mocking Strategy**:
- Mock `requests.Session` for API client tests
- Mock `FinnhubClient` for service tests
- Use fixtures for sample API responses

### 5.2 Integration Tests

**Test Scenarios**:
- End-to-end flow with real API call (requires API key)
- Error scenarios (network failure, invalid symbol)
- Output formatting

**Integration Test File**:
- `test_integration.py`: Full workflow tests

### 5.3 Test Execution

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_models.py

# Run with verbose output
pytest -v
```

---

## 6. Code Quality

### 6.1 Linting

**Tools**:
- `pylint`: Code quality checks
- `black`: Code formatting
- `mypy`: Type checking

**Configuration**:

`.pylintrc`:
```ini
[MASTER]
max-line-length=100

[MESSAGES CONTROL]
disable=
    missing-docstring,
    too-few-public-methods
```

`pyproject.toml`:
```toml
[tool.black]
line-length = 100
target-version = ['py39']

[tool.mypy]
python_version = "3.9"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
```

### 6.2 Pre-commit Checks

```bash
# Format code
black src/ tests/

# Lint code
pylint src/ tests/

# Type check
mypy src/

# Run tests
pytest
```

---

## 7. Deployment

### 7.1 Dependencies

**`requirements.txt`**:
```
requests>=2.31.0
python-dotenv>=1.0.0
```

**`requirements-dev.txt`**:
```
pytest>=7.4.0
pytest-cov>=4.1.0
pytest-mock>=3.11.1
black>=23.7.0
pylint>=2.17.5
mypy>=1.5.0
types-requests>=2.31.0
```

### 7.2 Installation

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 7.3 Configuration

```bash
# Set API key
export FINNHUB_API_KEY="your_api_key_here"

# Or use .env file
echo "FINNHUB_API_KEY=your_api_key_here" > .env
```

---

## 8. Security Considerations

### 8.1 API Key Management

- Never commit API keys to version control
- Use environment variables or .env files
- Add `.env` to `.gitignore`
- Validate API key format on load

### 8.2 Input Validation

- Sanitize ticker symbols (uppercase, alphanumeric only)
- Validate all user inputs before API calls
- Prevent command injection in shell operations

### 8.3 Data Privacy

- No PII collection or storage
- No logging of API keys
- Clear data retention policy (in-memory only)

---

## 9. Performance Considerations

### 9.1 API Call Optimization

- Single API call per ticker
- Connection pooling via requests.Session
- Configurable timeout (default 10s)

### 9.2 Data Processing

- Streaming JSON parsing for large responses
- Lazy evaluation where possible
- Memory-efficient data structures

### 9.3 Rate Limiting

- Track API call count
- Implement client-side rate limiter if needed
- Respect Finnhub rate limits (60/min)

---

## 10. Future Enhancements

### 10.1 Phase 2 Features

- Caching layer (Redis or local file cache)
- Batch processing for multiple tickers
- Historical data retrieval
- WebSocket support for real-time data

### 10.2 Phase 3 Features

- Database integration (PostgreSQL)
- RESTful API wrapper
- Web dashboard (React + TypeScript)
- Alerts and notifications

### 10.3 Technical Debt

- Add support for different API response formats
- Improve error messages with suggested fixes
- Add metrics and monitoring
- Performance profiling and optimization

---

## 11. Appendix

### A. API Response Examples

**Successful Response**:
```json
{
  "data": [
    {
      "expirationDate": "2026-01-16",
      "strike": 10.0,
      "type": "Call",
      "bid": 1.25,
      "ask": 1.30,
      "last": 1.27,
      "volume": 1500,
      "openInterest": 5000
    }
  ]
}
```

**Error Response**:
```json
{
  "error": "Invalid API key"
}
```

### B. Class Diagram

```
┌─────────────────────┐
│  FinnhubConfig      │
├─────────────────────┤
│ + api_key: str      │
│ + base_url: str     │
│ + timeout: int      │
└─────────────────────┘
          │
          │ uses
          ▼
┌─────────────────────┐
│  FinnhubClient      │
├─────────────────────┤
│ + get_option_chain()│
│ + close()           │
└─────────────────────┘
          │
          │ uses
          ▼
┌─────────────────────┐
│ OptionsChainService │
├─────────────────────┤
│ + get_options_chain()│
└─────────────────────┘
          │
          │ creates
          ▼
┌─────────────────────┐
│   OptionsChain      │
├─────────────────────┤
│ + symbol: str       │
│ + contracts: List   │
│ + get_calls()       │
│ + get_puts()        │
└─────────────────────┘
          │
          │ contains
          ▼
┌─────────────────────┐
│  OptionContract     │
├─────────────────────┤
│ + strike: float     │
│ + expiration: str   │
│ + bid: Optional[float]│
│ + ask: Optional[float]│
└─────────────────────┘
```

### C. Sequence Diagram

```
User -> main.py: python main.py F
main.py -> FinnhubConfig: from_env()
FinnhubConfig --> main.py: config
main.py -> FinnhubClient: __init__(config)
main.py -> OptionsChainService: __init__(client)
main.py -> OptionsChainService: get_options_chain("F")
OptionsChainService -> FinnhubClient: get_option_chain("F")
FinnhubClient -> Finnhub API: GET /stock/option-chain?symbol=F
Finnhub API --> FinnhubClient: JSON response
FinnhubClient --> OptionsChainService: Dict[str, Any]
OptionsChainService -> OptionsChainService: _validate_response()
OptionsChainService -> OptionsChainService: _parse_contracts()
OptionsChainService --> main.py: OptionsChain
main.py -> main.py: format_output()
main.py --> User: Display results
```

---

**Document Approval**

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Tech Lead | | | |
| Senior Developer | | | |
| QA Lead | | | |

