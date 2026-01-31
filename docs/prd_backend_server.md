# Product Requirements Document: Wheel Strategy Backend Server

**Version:** 2.0
**Date:** 2026-01-31
**Status:** Draft

---

## 1. Overview

### 1.1 Purpose

The Wheel Strategy Backend Server is a REST API server and background task processor for managing wheel strategy trading across multiple portfolios. It separates application logic from data persistence and processing, enabling multiple client interfaces (CLI, web, mobile) to interact with a centralized trading system.

### 1.2 Background

The current wheel_strategy_tool is a CLI application with direct database access. This architecture limits:
- Multi-client support (CLI only)
- Background processing (no automated monitoring)
- Scalability (tight coupling between UI and logic)
- Future expansion (web/mobile interfaces difficult to add)

The backend server addresses these limitations by:
- Exposing REST API for all operations
- Running background tasks for monitoring and automation
- Centralizing state management and data persistence
- Supporting multiple portfolios for organization

### 1.3 Goals

- **Separation of Concerns**: Decouple frontend(s) from backend logic and data
- **Automation**: Enable periodic price updates, risk monitoring, and opportunity scanning
- **Extensibility**: Plugin system for custom scheduled tasks
- **Multi-Portfolio**: Support multiple trading portfolios for organization
- **API-First**: All functionality accessible via REST API
- **Documentation**: Auto-generated OpenAPI documentation

### 1.4 Non-Goals

- Multi-user authentication (single-user system)
- Public internet deployment (local/LAN only)
- Real-time WebSockets (polling for now, WebSockets future enhancement)
- Multi-broker support (Schwab only for now)
- Automated order execution (recommendations only)

---

## 2. User Stories

### 2.1 Core User Stories

**US-1: Manage Portfolios**
> As a trader, I want to create multiple portfolios so that I can organize my wheels by strategy, account, or risk level.

**US-2: Access via API**
> As a developer, I want to interact with the system via REST API so that I can build custom clients (CLI, web, mobile).

**US-3: Automated Price Updates**
> As a trader, I want the system to automatically refresh prices for my open positions so that I always have current data without manual updates.

**US-4: Monitor Risk Automatically**
> As a trader, I want the system to automatically monitor my positions for assignment risk so that I'm alerted when positions move ITM.

**US-5: Historical Performance Tracking**
> As a trader, I want to see my win/loss ratio and cumulative P&L over time so that I can evaluate strategy effectiveness.

**US-6: Interactive API Documentation**
> As a developer, I want to explore the API through interactive documentation so that I can understand endpoints without reading separate docs.

### 2.2 Background Processing Stories

**US-7: Daily Snapshots**
> As a trader, I want the system to automatically create end-of-day snapshots so that I can track position evolution over time.

**US-8: Opportunity Scanning**
> As a trader, I want the system to scan for new opportunities on my tracked symbols so that I don't miss favorable entry points.

**US-9: Custom Automation**
> As an advanced user, I want to create custom scheduled tasks (plugins) so that I can automate my unique workflows.

**US-10: Task Management**
> As a trader, I want to configure when and how often background tasks run so that I can optimize for market hours and my preferences.

### 2.3 Migration Stories

**US-11: CLI Compatibility**
> As an existing user, I want my CLI commands to work unchanged so that I don't have to relearn the interface.

**US-12: Data Preservation**
> As an existing user, I want my historical trades and positions migrated to the new system so that I don't lose my performance history.

**US-13: Gradual Migration**
> As a developer, I want the ability to run old CLI (direct DB) or new CLI (API) modes so that I can test before fully migrating.

---

## 3. Functional Requirements

### 3.1 Portfolio Management

**FR-1: Portfolio CRUD**
- Create portfolio with name, description, default capital
- List all portfolios
- Get portfolio details with summary stats
- Update portfolio properties
- Delete portfolio (cascade delete wheels/trades)

**FR-2: Portfolio Summary**
- Total wheels in portfolio
- Total open positions
- Total capital allocated
- Total premium collected
- Win/loss ratio
- Overall P&L

**FR-3: Default Portfolio**
- Support concept of "default" portfolio for CLI
- If no portfolio specified, use default

### 3.2 Wheel Management (via API)

**FR-4: Wheel Lifecycle**
- Create/initialize wheel in portfolio
- Update wheel configuration (profile, capital)
- Delete wheel
- Get wheel state and details
- List wheels by portfolio

**FR-5: Multi-Portfolio Wheels**
- Same symbol can exist in multiple portfolios
- Each wheel is independent (separate state, trades)
- Portfolio-level aggregation

### 3.3 Trade Management (via API)

**FR-6: Trade Operations**
- Record trade (all existing functionality)
- Update trade metadata (notes, etc.)
- Close trade early
- Record expiration outcome
- List trades by wheel
- Get trade details

**FR-7: Trade History**
- Query trades by date range
- Filter by outcome (expired, assigned, closed)
- Export to CSV

### 3.4 Position Monitoring

**FR-8: Live Position Status**
- Current price (cached, auto-refreshed)
- Strike price
- Days to expiration (calendar and trading)
- Moneyness (ITM/OTM percentage)
- Risk level (LOW/MEDIUM/HIGH)
- Premium collected

**FR-9: Risk Assessment**
- Calculate risk based on moneyness
- Flag high-risk positions (ITM)
- Alert on approaching expiration (< 3 DTE)

**FR-10: Batch Position Status**
- Get status for all positions in portfolio
- Get status for all open positions (all portfolios)
- Filter by risk level, expiration date

### 3.5 Historical Tracking

**FR-11: Daily Snapshots**
- Create snapshot at specified time (default: 4:30 PM ET)
- Store: date, price, DTE, moneyness, risk level
- Associate with trade and wheel
- Query snapshots by date range

**FR-12: Trend Analysis**
- Price trend over time
- Moneyness evolution
- Risk level changes
- Time decay visualization data

**FR-13: Snapshot Management**
- Automatic daily snapshots via scheduler
- Manual snapshot creation via API
- Query latest snapshot for position

### 3.6 Performance Analytics

**FR-14: Wheel-Level Performance**
- Total premium collected
- Number of trades
- Winning trades (expired OTM)
- Losing trades (assigned)
- Win rate percentage
- Average premium per trade
- Total P&L (premium - losses on assignment)

**FR-15: Portfolio-Level Performance**
- Aggregate metrics across all wheels
- Period-based analysis (last 30/90/365 days)
- Comparison across portfolios

**FR-16: System-Wide Performance**
- Overall win/loss statistics
- Best/worst performing symbols
- Total premium collected (all time)
- Overall P&L

**FR-17: Performance Export**
- Export metrics to CSV
- Custom date ranges
- Portfolio or system-wide

### 3.7 Recommendations (via API)

**FR-18: Strike Recommendations**
- Get next trade recommendation for wheel
- Batch recommendations for multiple symbols
- Same logic as existing CLI (bias, profiles, warnings)

**FR-19: Opportunity Scanning**
- Scan tracked symbols for favorable setups
- Configurable criteria (IV rank, earnings proximity, etc.)
- Return ranked opportunities

### 3.8 Background Task System

**FR-20: Core Scheduled Tasks**
- **Price Refresh**: Update prices for open positions
  - Default: Every 5 minutes during market hours (9:30 AM - 4:00 PM ET)
  - Configurable interval
- **Daily Snapshots**: Create end-of-day snapshots
  - Default: Daily at 4:30 PM ET
  - Configurable time
- **Risk Monitoring**: Check for high-risk positions
  - Default: Every 15 minutes
  - Configurable interval
- **Opportunity Scanning**: Scan for new opportunities
  - Default: Daily at 9:45 AM ET
  - Configurable schedule

**FR-21: Task Configuration**
- Enable/disable individual tasks
- Modify schedule (interval or cron)
- Portfolio-specific or system-wide
- Persist configuration in database

**FR-22: Task Management API**
- List all scheduled jobs
- Get job details (next run, last run, status)
- Update job schedule
- Manually trigger job execution
- View job execution history

**FR-23: Market Hours Awareness**
- Automatically pause tasks outside market hours
- Configurable market hours (default: 9:30 AM - 4:00 PM ET)
- Weekend/holiday skip (use trading calendar)

### 3.9 Plugin System

**FR-24: Plugin Interface**
- Standard base class for plugins
- Required methods: name, default_schedule, execute
- Optional hooks: on_success, on_failure
- Access to context (positions, portfolios, services)

**FR-25: Plugin Registration**
- Dynamic plugin discovery (load from plugins/ directory)
- Manual registration via API
- Automatic scheduling on registration
- Plugin enable/disable

**FR-26: Plugin Management**
- List registered plugins
- Get plugin details
- Update plugin schedule
- Remove plugin

**FR-27: Built-in Plugin Examples**
- Earnings alert (notify when earnings within 7 days)
- Volatility spike detector
- Premium target tracker

### 3.10 API Documentation

**FR-28: OpenAPI Specification**
- Auto-generated from FastAPI
- Accurate request/response schemas
- Enum values documented
- Error responses documented

**FR-29: Swagger UI**
- Interactive API explorer at /docs
- Try-it-out functionality
- Authentication support (future)
- Example requests/responses

**FR-30: ReDoc Alternative**
- Alternative documentation UI at /redoc
- Better for printing/exporting

### 3.11 System Management

**FR-31: Health Check**
- Overall health status
- Database connectivity
- Schwab API connectivity
- Scheduler status
- Timestamp of check

**FR-32: System Info**
- Server version
- Uptime
- Database file size
- Number of portfolios/wheels/trades
- Active background jobs

**FR-33: Configuration Management**
- Get current configuration
- Update configuration (market hours, API keys, etc.)
- Restart required indicators
- Validate configuration before applying

---

## 4. Non-Functional Requirements

### 4.1 Performance

**NFR-1: Response Time**
- API endpoints respond within 200ms (excluding external API calls)
- Background tasks complete within allocated time window
- Database queries optimized with indexes

**NFR-2: Concurrent Requests**
- Support 10+ concurrent API requests
- Background tasks don't block API responses
- Use asyncio for non-blocking I/O

**NFR-3: Caching**
- Quote data cached for 5 minutes
- Options chain cached for 15 minutes
- Historical data cached for 24 hours

### 4.2 Reliability

**NFR-4: Error Handling**
- Graceful degradation when external APIs fail
- Background task failures logged, don't crash server
- Retry logic for transient failures (exponential backoff)

**NFR-5: Data Integrity**
- Database transactions for multi-step operations
- Foreign key constraints enforced
- Cascade deletes configured properly

**NFR-6: Uptime**
- Server runs continuously via systemd
- Auto-restart on crash
- Log rotation to prevent disk fill

### 4.3 Maintainability

**NFR-7: Code Quality**
- Type hints throughout
- Comprehensive docstrings
- Consistent naming conventions
- Separation of concerns (layers)

**NFR-8: Testing**
- Unit tests for business logic (80%+ coverage)
- Integration tests for API endpoints
- Mock external dependencies

**NFR-9: Logging**
- Structured logging (JSON format option)
- Different log levels (DEBUG, INFO, WARNING, ERROR)
- Sanitize sensitive data (tokens, keys)

### 4.4 Security

**NFR-10: Network Security**
- Listen on localhost or private network only
- No public exposure (firewall)
- Optional HTTPS via reverse proxy

**NFR-11: Data Protection**
- Schwab OAuth tokens encrypted at rest
- Database file permissions restricted
- No sensitive data in logs

**NFR-12: Input Validation**
- All API inputs validated via Pydantic
- SQL injection prevention (parameterized queries)
- Path traversal prevention

### 4.5 Usability

**NFR-13: API Design**
- RESTful conventions
- Consistent response formats
- Clear error messages
- Logical endpoint structure

**NFR-14: Documentation**
- OpenAPI spec complete and accurate
- Examples for all endpoints
- Error codes documented
- Migration guide for existing users

---

## 5. API Specification

### 5.1 Response Format

#### Success Response
```json
{
  "data": {
    // Response payload
  },
  "timestamp": "2026-01-31T12:00:00Z"
}
```

#### Error Response
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid strike price",
    "details": {
      "field": "strike",
      "value": -100,
      "constraint": "must be positive"
    }
  },
  "timestamp": "2026-01-31T12:00:00Z"
}
```

### 5.2 Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| VALIDATION_ERROR | 400 | Invalid request payload |
| NOT_FOUND | 404 | Resource not found |
| CONFLICT | 409 | Resource already exists |
| INVALID_STATE | 409 | Invalid state transition |
| EXTERNAL_API_ERROR | 502 | Schwab/Finnhub API error |
| INTERNAL_ERROR | 500 | Unexpected server error |

### 5.3 Pagination

For list endpoints returning many results:
```json
{
  "data": [],
  "pagination": {
    "page": 1,
    "page_size": 50,
    "total_items": 237,
    "total_pages": 5
  }
}
```

Query parameters: `?page=1&page_size=50`

### 5.4 Filtering and Sorting

```
GET /api/v1/trades?symbol=AAPL&outcome=expired&sort=-created_at
```

- `symbol`: Filter by symbol
- `outcome`: Filter by outcome
- `sort`: Sort field (`-` prefix for descending)

---

## 6. Data Models

### 6.1 Portfolio
```python
class Portfolio(BaseModel):
    id: str
    name: str
    description: Optional[str]
    default_capital: float
    created_at: datetime
    updated_at: datetime
```

### 6.2 Wheel
```python
class Wheel(BaseModel):
    id: str
    portfolio_id: str
    symbol: str
    state: WheelState
    shares: int
    capital_allocated: float
    starting_direction: Optional[str]
    profile: str
    created_at: datetime
    updated_at: datetime
```

### 6.3 Trade
```python
class Trade(BaseModel):
    id: str
    wheel_id: str
    symbol: str
    direction: str  # "put" or "call"
    strike: float
    expiration_date: str  # ISO format
    contracts: int
    total_premium: float
    outcome: TradeOutcome
    created_at: datetime
    expired_at: Optional[datetime]
    stock_price_at_expiry: Optional[float]
```

### 6.4 PositionStatus
```python
class PositionStatus(BaseModel):
    wheel_id: str
    symbol: str
    state: WheelState
    current_price: float
    strike: float
    expiration: str
    dte_calendar: int
    dte_trading: int
    moneyness: MoneynessData
    risk_level: str  # "LOW", "MEDIUM", "HIGH"
    risk_icon: str  # "🟢", "🟡", "🔴"
    premium_collected: float
    last_updated: datetime
```

### 6.5 Snapshot
```python
class Snapshot(BaseModel):
    id: str
    trade_id: str
    wheel_id: str
    snapshot_date: str  # ISO date
    current_price: float
    dte_calendar: int
    dte_trading: int
    moneyness_pct: float
    is_itm: bool
    risk_level: str
    created_at: datetime
```

### 6.6 PerformanceMetrics
```python
class PerformanceMetrics(BaseModel):
    portfolio_id: Optional[str]  # None for system-wide
    wheel_id: Optional[str]  # None for portfolio/system aggregate
    period_start: date
    period_end: date
    total_premium: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float  # Percentage
    average_premium: float
    total_pnl: float
```

---

## 7. Migration Strategy

### 7.1 Phase 1: Backend Foundation
**Duration:** 2 weeks

**Deliverables:**
- FastAPI application structure
- Database migration script (old -> new schema)
- Portfolio/Wheel/Trade CRUD endpoints
- OpenAPI documentation
- Health check endpoint

**Testing:**
- API endpoint tests
- Database migration tests
- Manual testing with Swagger UI

**Migration Impact:** None - backend only

### 7.2 Phase 2: Business Logic Integration
**Duration:** 2 weeks

**Deliverables:**
- Recommendation endpoints
- Position monitoring endpoints
- Connect WheelManager/RecommendEngine
- Repository layer with SQLAlchemy
- Error handling and validation

**Testing:**
- Integration tests with existing business logic
- API contract tests

**Migration Impact:** CLI can use API via `--api-mode` flag (optional)

### 7.3 Phase 3: Background Tasks
**Duration:** 2 weeks

**Deliverables:**
- APScheduler setup
- Core scheduled tasks (price refresh, snapshots, risk, opportunities)
- Task configuration persistence
- Scheduler management endpoints
- Market hours awareness

**Testing:**
- Task execution tests
- Schedule configuration tests
- Market hours logic tests

**Migration Impact:** New functionality, no CLI changes

### 7.4 Phase 4: Plugin System
**Duration:** 2 weeks

**Deliverables:**
- Plugin base class and interface
- Plugin registration and discovery
- Example plugins (earnings alert, etc.)
- Plugin management endpoints
- Plugin documentation

**Testing:**
- Plugin loading tests
- Plugin execution tests
- Custom plugin examples

**Migration Impact:** New functionality, no CLI changes

### 7.5 Phase 5: CLI Migration
**Duration:** 2 weeks

**Deliverables:**
- Refactor CLI to call REST API
- Remove direct database access
- Add portfolio selection (`--portfolio`)
- Maintain command compatibility
- Configuration file for API endpoint

**Testing:**
- CLI command tests (API mode)
- Backward compatibility tests
- User acceptance testing

**Migration Impact:** CLI uses API by default, can fall back to direct mode

### 7.6 Phase 6: Performance Analytics
**Duration:** 2 weeks

**Deliverables:**
- Performance calculation endpoints
- Historical snapshot endpoints
- Trend analysis endpoints
- Export functionality
- Dashboard data endpoints

**Testing:**
- Performance calculation tests
- Data aggregation tests
- Export format tests

**Migration Impact:** New CLI commands for analytics

### 7.7 Phase 7: Documentation & Polish
**Duration:** 1 week

**Deliverables:**
- User documentation (setup, configuration, usage)
- Developer documentation (API guide, plugin development)
- Migration guide for existing users
- Troubleshooting guide
- Video tutorial (optional)

**Testing:**
- Documentation review
- End-to-end user testing

**Migration Impact:** Documentation updates

---

## 8. Configuration

### 8.1 Server Configuration
```yaml
# config.yaml
server:
  host: "0.0.0.0"
  port: 8000
  workers: 1
  log_level: "INFO"

database:
  url: "sqlite:///data/wheel_strategy.db"
  echo: false  # SQL logging

scheduler:
  enabled: true
  timezone: "America/New_York"
  job_defaults:
    coalesce: false
    max_instances: 1

market_hours:
  open_hour: 9
  open_minute: 30
  close_hour: 16
  close_minute: 0
  timezone: "America/New_York"

external_apis:
  schwab:
    app_key: "${SCHWAB_APP_KEY}"
    app_secret: "${SCHWAB_APP_SECRET}"
    token_file: ".schwab_tokens.json"
  finnhub:
    api_key: "${FINNHUB_API_KEY}"
    enabled: true

caching:
  quote_ttl: 300  # 5 minutes
  chain_ttl: 900  # 15 minutes
  history_ttl: 86400  # 24 hours
```

### 8.2 CLI Configuration
```yaml
# ~/.wheel_strategy/config.yaml
api:
  enabled: true  # Use API mode
  base_url: "http://localhost:8000"
  timeout: 30

default_portfolio: "primary"

# Fallback to direct mode if API unavailable
fallback_to_direct: true
```

---

## 9. Success Metrics

### 9.1 Technical Metrics
- API response time < 200ms (95th percentile)
- Background task success rate > 99%
- Zero data loss during migration
- Test coverage > 80%

### 9.2 User Experience Metrics
- CLI commands work identically (100% compatibility)
- Migration takes < 1 hour
- Documentation clarity (user survey)
- Feature adoption rate (background tasks, portfolios)

### 9.3 Business Metrics
- Same or improved win rate
- Faster time to identify opportunities (automated scanning)
- Reduced manual monitoring time
- Support for more simultaneous positions

---

## 10. Risks and Mitigations

### 10.1 Migration Risks

**Risk:** Data loss during database migration
**Mitigation:**
- Backup before migration
- Automated migration script with validation
- Rollback procedure documented

**Risk:** CLI breaks during migration
**Mitigation:**
- Maintain direct-mode as fallback
- Phased rollout with opt-in API mode
- Comprehensive testing before switch

**Risk:** Background tasks interfere with API performance
**Mitigation:**
- Separate thread pool for scheduler
- Async I/O prevents blocking
- Task execution timeout limits
- Performance monitoring

### 10.2 Technical Risks

**Risk:** APScheduler state lost on restart
**Mitigation:**
- Persist job definitions in database
- Rebuild schedule on startup
- Idempotent task design

**Risk:** Schwab API rate limits exceeded
**Mitigation:**
- Caching with appropriate TTLs
- Batch API calls when possible
- Exponential backoff on errors

**Risk:** SQLite locking on concurrent writes
**Mitigation:**
- Write-ahead logging (WAL mode)
- Connection pool configuration
- Acceptable for single-user local deployment

---

## 11. Future Enhancements

### 11.1 Near-term (< 6 months)
- WebSocket endpoints for real-time updates
- Web UI (React dashboard)
- Mobile app (React Native)
- Enhanced analytics and charts
- Backtesting framework

### 11.2 Long-term (> 6 months)
- Multi-user authentication
- Cloud deployment support
- PostgreSQL option for multi-user
- Multi-broker integration
- Machine learning for strike optimization
- Paper trading mode
- Integration with accounting software
