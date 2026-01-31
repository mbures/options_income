# System Design Document: Wheel Strategy Backend Server

**Version:** 2.0
**Date:** 2026-01-31
**Status:** Draft

---

## 1. Architecture Overview

### 1.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Client Layer                             │
├─────────────────────────────────────────────────────────────────┤
│  CLI Client              │  Web UI (Future)   │  Mobile (Future) │
│  - wheel_strategy_tool   │  - React/Vue App   │  - Native App    │
│  - REST API calls        │  - REST API calls  │  - REST API calls│
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ HTTP/REST
┌─────────────────────────────────────────────────────────────────┐
│                    Backend Server (FastAPI)                      │
├─────────────────────────────────────────────────────────────────┤
│  REST API Layer                  │  OpenAPI Documentation        │
│  - Portfolio endpoints           │  - Auto-generated docs        │
│  - Trade endpoints               │  - Interactive UI (Swagger)   │
│  - Position endpoints            │  - Schema validation          │
│  - Performance endpoints         │                               │
│  - Monitoring endpoints          │                               │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Background Task Layer                         │
├─────────────────────────────────────────────────────────────────┤
│  APScheduler (asyncio)                                          │
│  - Periodic price refresh        │  - Plugin System             │
│  - Position monitoring           │  - Dynamic task registration │
│  - Opportunity scanning          │  - Configurable schedules    │
│  - Snapshot creation             │                              │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Business Logic Layer                        │
├──────────────────┬──────────────────┬───────────────────────────┤
│  WheelManager    │  RecommendEngine │  PerformanceTracker       │
│  - State machine │  - Strike select │  - Metrics calculation    │
│  - CRUD ops      │  - Bias logic    │  - Aggregation            │
│  - Validation    │  - Warnings      │  - Historical analysis    │
│  - Monitoring    │  - Multi-symbol  │  - Win/Loss tracking      │
└──────────────────┴──────────────────┴───────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Monitoring Layer                            │
├──────────────────┬──────────────────┬───────────────────────────┤
│  PositionMonitor │  PositionStatus  │  SnapshotService          │
│  - Live data     │  - DTE tracking  │  - Daily snapshots        │
│  - Moneyness     │  - Risk levels   │  - Historical trends      │
│  - Risk assess   │  - ITM/OTM calc  │  - Time series data       │
└──────────────────┴──────────────────┴───────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Data Access Layer                            │
├─────────────────────────────────────────────────────────────────┤
│  Repository Pattern (SQLAlchemy ORM)                            │
│  - PortfolioRepository           │  - SnapshotRepository        │
│  - WheelRepository               │  - PerformanceRepository     │
│  - TradeRepository               │  - ConfigRepository          │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Database Layer (SQLite)                      │
├─────────────────────────────────────────────────────────────────┤
│  Tables:                                                        │
│  - portfolios        │  - wheels          │  - trades           │
│  - snapshots         │  - performance     │  - scheduler_config │
│  - task_plugins      │  - audit_log       │                    │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                   External Services Layer                        │
├──────────────────┬──────────────────┬───────────────────────────┤
│  SchwabClient    │  FinnhubClient   │  PriceFetcher             │
│  - OAuth mgmt    │  - Market data   │  - Caching                │
│  - Auto refresh  │  - Options data  │  - Rate limiting          │
│  - Quote/Chain   │                  │                           │
└──────────────────┴──────────────────┴───────────────────────────┘
```

### 1.2 Component Responsibilities

| Layer | Component | Responsibility |
|-------|-----------|---------------|
| **API** | FastAPI App | HTTP routing, request/response handling, OpenAPI docs |
| **API** | Pydantic Models | Request/response validation, schema generation |
| **Background** | APScheduler | Periodic task scheduling, job management |
| **Background** | Plugin System | Dynamic task registration, extensibility |
| **Business** | WheelManager | State machine, orchestration, validation |
| **Business** | RecommendEngine | Strike selection, bias logic, multi-symbol |
| **Business** | PerformanceTracker | Win/loss tracking, metrics aggregation |
| **Monitoring** | PositionMonitor | Real-time status, risk assessment |
| **Monitoring** | SnapshotService | Historical tracking, time series |
| **Data** | Repositories | CRUD operations, query abstraction |
| **Database** | SQLite | Persistence, transactions, queries |
| **External** | Service Clients | API calls, caching, error handling |

---

## 2. REST API Design

### 2.1 API Structure

**Base URL:** `http://localhost:8000/api/v1`

**OpenAPI Docs:** `http://localhost:8000/docs` (Swagger UI)

### 2.2 Endpoint Groups

#### Portfolio Endpoints
```
GET    /portfolios                    # List all portfolios
POST   /portfolios                    # Create portfolio
GET    /portfolios/{id}               # Get portfolio details
PUT    /portfolios/{id}               # Update portfolio
DELETE /portfolios/{id}               # Delete portfolio
GET    /portfolios/{id}/summary       # Portfolio summary stats
```

#### Wheel Endpoints
```
GET    /portfolios/{id}/wheels        # List wheels in portfolio
POST   /portfolios/{id}/wheels        # Create/initialize wheel
GET    /wheels/{id}                   # Get wheel details
PUT    /wheels/{id}                   # Update wheel config
DELETE /wheels/{id}                   # Delete wheel
GET    /wheels/{id}/state             # Get current state
```

#### Trade Endpoints
```
GET    /wheels/{id}/trades            # List trades for wheel
POST   /wheels/{id}/trades            # Record new trade
GET    /trades/{id}                   # Get trade details
PUT    /trades/{id}                   # Update trade (notes, etc.)
DELETE /trades/{id}                   # Delete trade
POST   /trades/{id}/expire            # Record expiration outcome
POST   /trades/{id}/close             # Close trade early
```

#### Recommendation Endpoints
```
GET    /wheels/{id}/recommend         # Get next trade recommendation
POST   /wheels/recommend/batch        # Batch recommendations for multiple symbols
```

#### Position Monitoring Endpoints
```
GET    /wheels/{id}/position          # Current position status (live data)
GET    /wheels/{id}/risk              # Risk assessment
GET    /portfolios/{id}/positions     # All positions in portfolio
GET    /positions/open                # All open positions (all portfolios)
```

#### Historical Tracking Endpoints
```
GET    /wheels/{id}/snapshots         # Historical snapshots
GET    /wheels/{id}/snapshots/latest  # Most recent snapshot
POST   /wheels/{id}/snapshots         # Create snapshot (manual)
GET    /wheels/{id}/trend             # Price/moneyness trend analysis
```

**Query Parameters for `/snapshots`:**
- `start_date`: ISO date (YYYY-MM-DD)
- `end_date`: ISO date (YYYY-MM-DD)
- `limit`: Max number of snapshots to return
- `offset`: Pagination offset

**Query Parameters for `/trend`:**
- `period`: "7d", "30d", "90d", "all", or custom range
- `interval`: "daily", "weekly" (for data point granularity)
- `metrics`: Comma-separated list ("price", "moneyness", "risk")

#### Performance Endpoints
```
GET    /wheels/{id}/performance       # Wheel-level performance
GET    /portfolios/{id}/performance   # Portfolio-level performance
GET    /performance/aggregate         # System-wide performance
GET    /performance/win-loss          # Win/loss ratios
GET    /performance/export            # Export to CSV
```

#### Scheduler Endpoints
```
GET    /scheduler/jobs                # List scheduled jobs
GET    /scheduler/jobs/{id}           # Get job details
PUT    /scheduler/jobs/{id}           # Update job schedule
POST   /scheduler/jobs/{id}/trigger   # Manually trigger job
GET    /scheduler/history             # Job execution history
```

#### System Endpoints
```
GET    /health                        # Health check
GET    /info                          # Server info (version, uptime)
GET    /config                        # System configuration
PUT    /config                        # Update configuration
```

### 2.3 Request/Response Examples

#### Create Portfolio
```http
POST /api/v1/portfolios
Content-Type: application/json

{
  "name": "Primary Trading",
  "description": "Main wheel strategy portfolio",
  "default_capital": 50000
}
```

Response:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Primary Trading",
  "description": "Main wheel strategy portfolio",
  "default_capital": 50000,
  "created_at": "2026-01-31T12:00:00Z",
  "updated_at": "2026-01-31T12:00:00Z"
}
```

#### Get Position Status
```http
GET /api/v1/wheels/abc-123/position
```

Response:
```json
{
  "wheel_id": "abc-123",
  "symbol": "AAPL",
  "state": "shares_call_open",
  "current_price": 258.98,
  "strike": 267.50,
  "expiration": "2026-02-02",
  "dte_calendar": 2,
  "dte_trading": 1,
  "moneyness": {
    "is_itm": false,
    "is_otm": true,
    "pct": -3.2,
    "label": "OTM by 3.2%"
  },
  "risk_level": "MEDIUM",
  "risk_icon": "🟡",
  "premium_collected": 148.00,
  "last_updated": "2026-01-31T12:30:00Z"
}
```

#### Get Historical Snapshots
```http
GET /api/v1/wheels/abc-123/snapshots?start_date=2026-01-01&end_date=2026-01-31
```

Response:
```json
{
  "wheel_id": "abc-123",
  "symbol": "AAPL",
  "snapshots": [
    {
      "id": "snap-001",
      "snapshot_date": "2026-01-30",
      "current_price": 257.50,
      "dte_calendar": 3,
      "dte_trading": 2,
      "moneyness_pct": -3.7,
      "is_itm": false,
      "risk_level": "MEDIUM",
      "created_at": "2026-01-30T16:30:00Z"
    },
    {
      "id": "snap-002",
      "snapshot_date": "2026-01-31",
      "current_price": 258.98,
      "dte_calendar": 2,
      "dte_trading": 1,
      "moneyness_pct": -3.2,
      "is_itm": false,
      "risk_level": "MEDIUM",
      "created_at": "2026-01-31T16:30:00Z"
    }
  ],
  "total_count": 2
}
```

#### Get Trend Analysis
```http
GET /api/v1/wheels/abc-123/trend?period=7d&interval=daily&metrics=price,moneyness,risk
```

Response:
```json
{
  "wheel_id": "abc-123",
  "symbol": "AAPL",
  "period": "7d",
  "interval": "daily",
  "data_points": [
    {
      "date": "2026-01-25",
      "price": 255.00,
      "moneyness_pct": -4.9,
      "risk_level": "LOW"
    },
    {
      "date": "2026-01-26",
      "price": 256.50,
      "moneyness_pct": -4.1,
      "risk_level": "MEDIUM"
    },
    {
      "date": "2026-01-27",
      "price": 258.00,
      "moneyness_pct": -3.5,
      "risk_level": "MEDIUM"
    }
  ],
  "summary": {
    "price_change": 3.98,
    "price_change_pct": 1.56,
    "moneyness_trend": "approaching_strike",
    "risk_progression": "increasing"
  }
}
```

---

## 3. Background Task System

### 3.1 APScheduler Integration

The system uses APScheduler with asyncio backend for scheduled tasks. Tasks are persisted using SQLAlchemy jobstore, allowing recovery after server restart.

**Key Configuration:**
- **Jobstore**: SQLite-based persistence
- **Executor**: AsyncIO executor for non-blocking execution
- **Timezone**: Configurable (default: America/New_York)
- **Lifecycle**: Started on FastAPI app startup, gracefully shut down on exit

### 3.2 Core Scheduled Tasks

#### Task 1: Refresh Position Prices
**Purpose:** Update current prices for all open positions
**Default Schedule:** Every 5 minutes during market hours
**Configurable:** Yes, per portfolio or system-wide

**Behavior:**
- Fetch all open positions from database
- Batch fetch current prices from Schwab API
- Update position cache with new prices
- Log failures without stopping other updates

#### Task 2: Create Daily Snapshots
**Purpose:** Capture end-of-day position state for historical tracking
**Default Schedule:** Daily at 4:30 PM ET (after market close)
**Configurable:** Yes

**Behavior:**
- Fetch all open positions
- Create snapshot record for each position
- Store: date, price, DTE, moneyness, risk level
- Skip if market closed or no open positions

#### Task 3: Scan for Opportunities
**Purpose:** Identify favorable wheel entry/continuation opportunities
**Default Schedule:** Daily at 9:45 AM ET (after market open)
**Configurable:** Yes

**Behavior:**
- Get list of tracked symbols (from config or active portfolios)
- Generate recommendations for each symbol
- Filter for favorable setups (configurable criteria)
- Log opportunities for review

#### Task 4: Risk Monitoring
**Purpose:** Identify high-risk positions requiring attention
**Default Schedule:** Every 15 minutes
**Configurable:** Yes

**Behavior:**
- Check all open positions for risk status
- Flag positions that are:
  - In-the-money (ITM)
  - Near expiration (< 3 DTE)
  - Significant moneyness change
- Log warnings/alerts

### 3.3 Plugin System Architecture

The plugin system allows dynamic registration of custom scheduled tasks.

#### Plugin Interface Specification

**Required Properties:**
- `name`: Unique identifier for the plugin
- `default_schedule`: Schedule configuration (interval or cron format)

**Required Methods:**
- `execute(context)`: Main task logic (async)

**Optional Hooks:**
- `on_success(context)`: Called after successful execution
- `on_failure(error, context)`: Called after failed execution
- `on_startup()`: Called when plugin is registered

**Context Provided:**
- Database session
- Current open positions
- System configuration
- Service clients (Schwab, monitoring, etc.)

#### Plugin Registration Flow

1. Plugin discovered from `plugins/` directory or registered via API
2. Plugin validated against interface specification
3. Plugin scheduled with APScheduler using default or custom schedule
4. Plugin persisted to database for recovery after restart
5. Plugin execution wrapped with error handling and logging

#### Example Plugin Configurations

**Earnings Alert Plugin:**
- Name: `earnings_alert`
- Schedule: Daily at 8:00 AM
- Purpose: Alert when positions have earnings within 7 days

**Volatility Spike Plugin:**
- Name: `volatility_spike`
- Schedule: Every 30 minutes
- Purpose: Detect unusual IV changes in open positions

**Premium Target Plugin:**
- Name: `premium_target`
- Schedule: Daily at 4:45 PM
- Purpose: Track progress toward monthly premium goals

### 3.4 Task Configuration

#### Database Schema
```sql
CREATE TABLE scheduler_config (
    id INTEGER PRIMARY KEY,
    portfolio_id TEXT,  -- NULL for system-wide
    task_name TEXT NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    schedule_type TEXT NOT NULL,  -- 'interval' or 'cron'
    schedule_params TEXT NOT NULL,  -- JSON
    last_run TIMESTAMP,
    next_run TIMESTAMP,
    UNIQUE(portfolio_id, task_name)
);
```

#### Configuration API Specification

**Update Job Schedule:**
```http
PUT /api/v1/scheduler/jobs/{job_id}
Content-Type: application/json

{
  "enabled": true,
  "schedule_type": "interval",
  "schedule_params": {
    "minutes": 10
  }
}
```

**Trigger Job Manually:**
```http
POST /api/v1/scheduler/jobs/{job_id}/trigger
```

**Get Job History:**
```http
GET /api/v1/scheduler/history?job_id={job_id}&limit=50
```

Response:
```json
{
  "job_id": "refresh_prices",
  "history": [
    {
      "execution_id": "exec-001",
      "started_at": "2026-01-31T10:00:00Z",
      "completed_at": "2026-01-31T10:00:03Z",
      "status": "success",
      "duration_seconds": 3.2,
      "message": "Updated 5 positions"
    },
    {
      "execution_id": "exec-002",
      "started_at": "2026-01-31T10:05:00Z",
      "completed_at": "2026-01-31T10:05:02Z",
      "status": "success",
      "duration_seconds": 2.8,
      "message": "Updated 5 positions"
    }
  ]
}
```

---

## 4. Database Schema

### 4.1 Core Tables

#### portfolios
```sql
CREATE TABLE portfolios (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    default_capital REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### wheels (enhanced)
```sql
CREATE TABLE wheels (
    id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    state TEXT NOT NULL,
    shares INTEGER DEFAULT 0,
    capital_allocated REAL DEFAULT 0,
    starting_direction TEXT,
    profile TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE,
    UNIQUE(portfolio_id, symbol)
);
```

#### trades (unchanged)
```sql
CREATE TABLE trades (
    id TEXT PRIMARY KEY,
    wheel_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    strike REAL NOT NULL,
    expiration_date TEXT NOT NULL,
    contracts INTEGER NOT NULL,
    total_premium REAL NOT NULL,
    outcome TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expired_at TIMESTAMP,
    stock_price_at_expiry REAL,
    FOREIGN KEY (wheel_id) REFERENCES wheels(id) ON DELETE CASCADE
);
```

#### snapshots (enhanced)
```sql
CREATE TABLE snapshots (
    id TEXT PRIMARY KEY,
    trade_id TEXT NOT NULL,
    wheel_id TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    current_price REAL NOT NULL,
    dte_calendar INTEGER NOT NULL,
    dte_trading INTEGER NOT NULL,
    moneyness_pct REAL NOT NULL,
    is_itm BOOLEAN NOT NULL,
    risk_level TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (trade_id) REFERENCES trades(id) ON DELETE CASCADE,
    FOREIGN KEY (wheel_id) REFERENCES wheels(id) ON DELETE CASCADE,
    UNIQUE(trade_id, snapshot_date)
);

CREATE INDEX idx_snapshots_date ON snapshots(snapshot_date);
CREATE INDEX idx_snapshots_wheel ON snapshots(wheel_id, snapshot_date);
```

#### performance_metrics (new)
```sql
CREATE TABLE performance_metrics (
    id TEXT PRIMARY KEY,
    portfolio_id TEXT,  -- NULL for system-wide
    wheel_id TEXT,      -- NULL for portfolio/system aggregate
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    total_premium REAL NOT NULL,
    total_trades INTEGER NOT NULL,
    winning_trades INTEGER NOT NULL,
    losing_trades INTEGER NOT NULL,
    win_rate REAL NOT NULL,
    average_premium REAL NOT NULL,
    total_pnl REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE,
    FOREIGN KEY (wheel_id) REFERENCES wheels(id) ON DELETE CASCADE
);

CREATE INDEX idx_performance_period ON performance_metrics(period_start, period_end);
CREATE INDEX idx_performance_portfolio ON performance_metrics(portfolio_id);
```

---

## 5. Technology Stack

### 5.1 Backend Framework
- **FastAPI**: Modern async web framework with automatic OpenAPI generation
- **Uvicorn**: ASGI server for production deployment
- **Pydantic**: Data validation and serialization with type hints

### 5.2 Background Tasks
- **APScheduler**: Asyncio-based job scheduling with persistence
- **AsyncIO**: Native Python async/await for non-blocking operations

### 5.3 Database
- **SQLite**: Embedded database (suitable for single-user deployment)
- **SQLAlchemy**: ORM for data access with async support
- **Alembic**: Database migrations and version control

### 5.4 External Services
- **httpx**: Async HTTP client for external API calls
- **SchwabClient**: Existing OAuth + market data integration
- **FinnhubClient**: Supplementary market data (optional)

### 5.5 Testing
- **pytest**: Test framework with fixtures and parametrization
- **pytest-asyncio**: Async test support
- **httpx.AsyncClient**: API endpoint testing
- **pytest-mock**: Mocking external dependencies

### 5.6 Development Tools
- **Black**: Code formatting (PEP 8 compliance)
- **Pylint**: Static code analysis and linting
- **mypy**: Static type checking

---

## 6. Deployment Architecture

### 6.1 Single Server Deployment

```
┌─────────────────────────────────────────┐
│  Local/LAN Network                       │
│                                          │
│  ┌─────────────────────────────────┐   │
│  │  Backend Server                  │   │
│  │  (FastAPI + APScheduler)         │   │
│  │  Port: 8000                      │   │
│  │  ├─ API Endpoints                │   │
│  │  ├─ Background Tasks             │   │
│  │  └─ Database (SQLite)            │   │
│  └─────────────────────────────────┘   │
│                ▲                         │
│                │ HTTP                    │
│  ┌─────────────┴──────────────────┐    │
│  │  Clients                        │    │
│  │  ├─ CLI (wheel_strategy_tool)  │    │
│  │  ├─ Web Browser (Swagger UI)   │    │
│  │  └─ Future Web UI               │    │
│  └──────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

### 6.2 Process Management

#### systemd Service Configuration
```ini
[Unit]
Description=Wheel Strategy Backend Server
After=network.target

[Service]
Type=simple
User=trader
WorkingDirectory=/opt/wheel_strategy
Environment="PATH=/opt/wheel_strategy/venv/bin"
ExecStart=/opt/wheel_strategy/venv/bin/uvicorn \
    src.server.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 6.3 Configuration

#### Environment Variables
```bash
# Server
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
LOG_LEVEL=INFO

# Database
DATABASE_URL=sqlite:///data/wheel_strategy.db

# External APIs
SCHWAB_APP_KEY=xxx
SCHWAB_APP_SECRET=xxx
FINNHUB_API_KEY=xxx

# Scheduler
SCHEDULER_ENABLED=true
MARKET_OPEN_HOUR=9
MARKET_CLOSE_HOUR=16
```

#### Application Configuration (YAML)
```yaml
server:
  host: "0.0.0.0"
  port: 8000
  workers: 1
  log_level: "INFO"

database:
  url: "sqlite:///data/wheel_strategy.db"
  echo: false

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

tasks:
  price_refresh:
    enabled: true
    interval_minutes: 5
  daily_snapshot:
    enabled: true
    cron_hour: 16
    cron_minute: 30
  risk_monitoring:
    enabled: true
    interval_minutes: 15
  opportunity_scanning:
    enabled: true
    cron_hour: 9
    cron_minute: 45
```

---

## 7. Migration Strategy

### 7.1 Phase 1: Backend Foundation (Sprint 1-2)
**Goal:** Set up server infrastructure and core API

**Deliverables:**
- FastAPI application skeleton
- OpenAPI documentation
- Health/info endpoints
- Database migration from current to new schema
- Portfolio CRUD endpoints
- Wheel CRUD endpoints
- Basic trade endpoints

**Migration Impact:** None - backend only, CLI unchanged

### 7.2 Phase 2: Business Logic Integration (Sprint 3-4)
**Goal:** Connect existing business logic to API

**Deliverables:**
- Recommendation endpoints
- Position monitoring endpoints
- Performance tracking endpoints
- Integrate WheelManager, RecommendEngine
- Repository layer with SQLAlchemy

**Migration Impact:** CLI can optionally use API via config flag

### 7.3 Phase 3: Background Tasks (Sprint 5-6)
**Goal:** Implement scheduled tasks and monitoring

**Deliverables:**
- APScheduler integration
- Core scheduled tasks (price refresh, snapshots, risk)
- Plugin system framework
- Scheduler management endpoints
- Task configuration persistence

**Migration Impact:** New functionality, CLI unchanged

### 7.4 Phase 4: CLI Migration (Sprint 7-8)
**Goal:** Convert CLI to API client

**Deliverables:**
- Refactor CLI to call REST API
- Remove direct database access from CLI
- Add portfolio selection to CLI
- Maintain command compatibility
- Update documentation

**Migration Impact:** CLI behavior identical, but uses API backend

### 7.5 Phase 5: Historical Analytics (Sprint 9-10)
**Goal:** Enhanced performance tracking and analysis

**Deliverables:**
- Historical snapshot endpoints
- Trend analysis endpoints
- Win/loss tracking
- Performance aggregation
- Export functionality

**Migration Impact:** New features available in CLI and API

### 7.6 Phase 6: Advanced Features (Sprint 11+)
**Goal:** Extended functionality

**Deliverables:**
- Custom plugin examples
- Multi-account support (future)
- WebSocket endpoints (future)
- Advanced analytics dashboards (future)

---

## 8. Security Considerations

### 8.1 Network Security
- **Local/LAN only**: No public internet exposure
- **Firewall rules**: Restrict to trusted network (192.168.x.x/24)
- **HTTPS**: Optional, use reverse proxy (nginx) for TLS if desired

### 8.2 Authentication (Future)
- Currently single-user, no auth required
- Future: JWT tokens, API keys for multi-user scenarios

### 8.3 Data Protection
- **Sensitive data**: Schwab OAuth tokens encrypted at rest
- **Database**: File permissions restricted to service user (0600)
- **Logs**: Sanitize sensitive data (tokens, account numbers, PII)

### 8.4 Input Validation
- **Pydantic models**: Automatic request validation with type coercion
- **SQLAlchemy**: Parameterized queries prevent SQL injection
- **Rate limiting**: Optional via FastAPI middleware (future enhancement)

---

## 9. Monitoring and Observability

### 9.1 Logging Strategy

**Log Levels:**
- **DEBUG**: Detailed diagnostic info (SQL queries, cache hits/misses)
- **INFO**: Normal operations (API requests, task executions)
- **WARNING**: Recoverable issues (API failures, retry attempts)
- **ERROR**: Serious problems (task failures, database errors)

**Log Output:**
- Rotating file handler (10MB max, 5 backups)
- Console output for development
- Structured logging with timestamps, levels, module names

### 9.2 Health Check Specification

**Endpoint:** `GET /health`

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-01-31T12:00:00Z",
  "checks": {
    "database": {
      "status": "up",
      "response_time_ms": 2
    },
    "schwab_api": {
      "status": "up",
      "last_successful_call": "2026-01-31T11:59:30Z"
    },
    "scheduler": {
      "status": "running",
      "active_jobs": 4,
      "next_run": "2026-01-31T12:05:00Z"
    }
  }
}
```

**Status Codes:**
- 200: All systems operational
- 503: One or more critical systems down

### 9.3 Metrics Collection

**API Metrics:**
- Request/response times (p50, p95, p99)
- Endpoint usage counts
- Error rates by endpoint
- Concurrent request count

**Background Task Metrics:**
- Task execution times
- Success/failure rates
- Queue depth (if applicable)
- Last execution timestamps

**Database Metrics:**
- Query execution times
- Connection pool usage
- Database file size
- Index hit rates

---

## 10. Testing Strategy

### 10.1 Unit Tests
- Business logic components (WheelManager, RecommendEngine)
- Repository layer methods
- Scheduled task logic
- Utility functions and helpers

**Coverage Target:** >80%

### 10.2 Integration Tests
- API endpoints (using FastAPI TestClient)
- Database operations (using test database)
- External service integrations (mocked)
- End-to-end workflows

### 10.3 End-to-End Tests
- Full user scenarios (create wheel → record trade → expire)
- CLI + API integration
- Background task execution
- Data consistency across components

---

## 11. Documentation

### 11.1 OpenAPI/Swagger
- Auto-generated from FastAPI decorators
- Interactive API explorer at `/docs`
- Request/response examples
- Schema documentation with descriptions

### 11.2 User Documentation
- Installation and setup guide
- API usage examples
- CLI migration guide
- Configuration reference
- Troubleshooting common issues

### 11.3 Developer Documentation
- Architecture overview (this document)
- Plugin development guide
- Contributing guidelines
- Code style conventions
- Testing procedures

---

## 12. Future Enhancements

### 12.1 Short-term (< 6 months)
- WebSocket support for real-time position updates
- Enhanced analytics dashboard (web UI)
- Mobile app (React Native)
- Multi-account support (multiple Schwab accounts)
- Advanced charting for trends

### 12.2 Long-term (6-12 months)
- Cloud deployment option (Docker + orchestration)
- Multi-user authentication and authorization
- Advanced backtesting framework
- Machine learning for strike optimization
- Integration with additional brokers (TD Ameritrade, IBKR)
- Paper trading mode

---

**Document End**
