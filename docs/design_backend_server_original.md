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

---

## 3. Background Task System

### 3.1 APScheduler Integration

#### Scheduler Configuration
```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

jobstores = {
    'default': SQLAlchemyJobStore(url='sqlite:///scheduler.db')
}

scheduler = AsyncIOScheduler(jobstores=jobstores)
```

#### Startup/Shutdown Hooks
```python
@app.on_event("startup")
async def startup_event():
    scheduler.start()
    await register_periodic_tasks()

@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()
```

### 3.2 Core Scheduled Tasks

#### Task 1: Refresh Position Prices
```python
@scheduler.scheduled_job('interval', minutes=5, id='refresh_prices')
async def refresh_position_prices():
    """Update current prices for all open positions."""
    positions = await get_all_open_positions()
    for position in positions:
        try:
            await update_position_price(position)
        except Exception as e:
            logger.error(f"Failed to refresh {position.symbol}: {e}")
```

**Default Schedule:** Every 5 minutes during market hours
**Configurable:** Yes, per portfolio or system-wide

#### Task 2: Create Daily Snapshots
```python
@scheduler.scheduled_job('cron', hour=16, minute=30, id='daily_snapshots')
async def create_daily_snapshots():
    """Create end-of-day snapshots for all open positions."""
    positions = await get_all_open_positions()
    for position in positions:
        try:
            await create_position_snapshot(position)
        except Exception as e:
            logger.error(f"Failed to snapshot {position.symbol}: {e}")
```

**Default Schedule:** Daily at 4:30 PM ET (after market close)
**Configurable:** Yes

#### Task 3: Scan for Opportunities
```python
@scheduler.scheduled_job('cron', hour=9, minute=45, id='scan_opportunities')
async def scan_opportunities():
    """Scan for new wheel opportunities across tracked symbols."""
    symbols = await get_tracked_symbols()
    for symbol in symbols:
        try:
            recommendation = await generate_recommendation(symbol)
            if recommendation.is_favorable():
                await notify_opportunity(symbol, recommendation)
        except Exception as e:
            logger.error(f"Failed to scan {symbol}: {e}")
```

**Default Schedule:** Daily at 9:45 AM ET (after market open)
**Configurable:** Yes

#### Task 4: Risk Monitoring
```python
@scheduler.scheduled_job('interval', minutes=15, id='risk_monitor')
async def monitor_risk():
    """Check for high-risk positions (ITM, close to expiration)."""
    positions = await get_all_open_positions()
    for position in positions:
        try:
            risk = await assess_risk(position)
            if risk.level == RiskLevel.HIGH:
                await flag_high_risk_position(position, risk)
        except Exception as e:
            logger.error(f"Failed to assess risk for {position.symbol}: {e}")
```

**Default Schedule:** Every 15 minutes
**Configurable:** Yes

### 3.3 Plugin System Architecture

#### Plugin Interface
```python
from abc import ABC, abstractmethod
from typing import Dict, Any

class ScheduledTaskPlugin(ABC):
    """Base class for scheduled task plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique plugin name."""
        pass

    @property
    @abstractmethod
    def default_schedule(self) -> Dict[str, Any]:
        """Default schedule (cron or interval format)."""
        pass

    @abstractmethod
    async def execute(self, context: Dict[str, Any]) -> None:
        """Execute the task."""
        pass

    async def on_success(self, context: Dict[str, Any]) -> None:
        """Hook called after successful execution."""
        pass

    async def on_failure(self, error: Exception, context: Dict[str, Any]) -> None:
        """Hook called after failed execution."""
        pass
```

#### Plugin Registration
```python
class PluginManager:
    """Manages dynamic plugin registration and execution."""

    def __init__(self, scheduler: AsyncIOScheduler):
        self.scheduler = scheduler
        self.plugins: Dict[str, ScheduledTaskPlugin] = {}

    def register(self, plugin: ScheduledTaskPlugin):
        """Register a new plugin."""
        self.plugins[plugin.name] = plugin

        # Add to scheduler
        schedule = plugin.default_schedule
        if 'interval' in schedule:
            self.scheduler.add_job(
                self._execute_plugin,
                'interval',
                args=[plugin.name],
                id=plugin.name,
                **schedule
            )
        elif 'cron' in schedule:
            self.scheduler.add_job(
                self._execute_plugin,
                'cron',
                args=[plugin.name],
                id=plugin.name,
                **schedule['cron']
            )

    async def _execute_plugin(self, plugin_name: str):
        """Execute a plugin with error handling."""
        plugin = self.plugins[plugin_name]
        try:
            context = await self._build_context()
            await plugin.execute(context)
            await plugin.on_success(context)
        except Exception as e:
            logger.error(f"Plugin {plugin_name} failed: {e}")
            await plugin.on_failure(e, context)
```

#### Example Custom Plugin
```python
class EarningsAlertPlugin(ScheduledTaskPlugin):
    """Alert when positions have earnings within 7 days."""

    @property
    def name(self) -> str:
        return "earnings_alert"

    @property
    def default_schedule(self) -> Dict[str, Any]:
        return {'interval': {'hours': 24}}  # Daily

    async def execute(self, context: Dict[str, Any]) -> None:
        positions = context['open_positions']
        for position in positions:
            earnings = await get_next_earnings(position.symbol)
            if earnings and earnings.days_until <= 7:
                await send_earnings_alert(position, earnings)
```

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

#### Configuration API
```python
@router.put("/scheduler/jobs/{job_id}")
async def update_job_schedule(
    job_id: str,
    schedule: ScheduleUpdate
) -> JobResponse:
    """Update job schedule configuration."""
    # Update database
    await config_repo.update_schedule(job_id, schedule)

    # Update running job
    scheduler.reschedule_job(
        job_id,
        trigger=schedule.trigger_type,
        **schedule.params
    )

    return await get_job_details(job_id)
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
```

---

## 5. Technology Stack

### 5.1 Backend Framework
- **FastAPI**: Modern async web framework
- **Uvicorn**: ASGI server
- **Pydantic**: Data validation and serialization

### 5.2 Background Tasks
- **APScheduler**: Asyncio-based job scheduling
- **AsyncIO**: Native Python async/await

### 5.3 Database
- **SQLite**: Embedded database
- **SQLAlchemy**: ORM for data access
- **Alembic**: Database migrations

### 5.4 External Services
- **httpx**: Async HTTP client
- **SchwabClient**: OAuth + market data
- **FinnhubClient**: Supplementary data (future)

### 5.5 Testing
- **pytest**: Test framework
- **pytest-asyncio**: Async test support
- **httpx.AsyncClient**: API testing

### 5.6 Development Tools
- **Black**: Code formatting
- **Pylint**: Linting
- **mypy**: Type checking

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

#### systemd Service
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
- **Firewall rules**: Restrict to trusted network
- **HTTPS**: Optional, use reverse proxy (nginx) for TLS

### 8.2 Authentication (Future)
- Currently single-user, no auth required
- Future: JWT tokens, API keys for multi-user

### 8.3 Data Protection
- **Sensitive data**: Schwab OAuth tokens encrypted at rest
- **Database**: File permissions restricted to service user
- **Logs**: Sanitize sensitive data (tokens, account numbers)

### 8.4 Input Validation
- **Pydantic models**: Automatic validation
- **SQLAlchemy**: Parameterized queries (SQL injection protection)
- **Rate limiting**: Optional, via FastAPI middleware

---

## 9. Monitoring and Observability

### 9.1 Logging
```python
import logging
from logging.handlers import RotatingFileHandler

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler('logs/server.log', maxBytes=10485760, backupCount=5),
        logging.StreamHandler()
    ]
)
```

### 9.2 Health Checks
```python
@router.get("/health")
async def health_check() -> HealthResponse:
    """Comprehensive health check."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(),
        "checks": {
            "database": await check_database(),
            "schwab_api": await check_schwab_connectivity(),
            "scheduler": scheduler.running
        }
    }
```

### 9.3 Metrics
- Request/response times
- API endpoint usage
- Background task execution times
- Error rates
- Database query performance

---

## 10. Testing Strategy

### 10.1 Unit Tests
- Business logic components
- Repository layer
- Scheduled tasks
- Utility functions

### 10.2 Integration Tests
- API endpoints (FastAPI TestClient)
- Database operations
- External service mocks

### 10.3 End-to-End Tests
- Full workflow scenarios
- CLI + API integration
- Background task execution

---

## 11. Documentation

### 11.1 OpenAPI/Swagger
- Auto-generated from FastAPI
- Interactive API explorer
- Request/response examples
- Schema documentation

### 11.2 User Documentation
- API usage guide
- CLI migration guide
- Configuration reference
- Troubleshooting guide

### 11.3 Developer Documentation
- Architecture overview (this document)
- Plugin development guide
- Contributing guidelines
- Code conventions

---

## 12. Future Enhancements

### 12.1 Short-term (6 months)
- WebSocket support for real-time updates
- Enhanced analytics dashboard
- Mobile app (React Native)
- Multi-account support

### 12.2 Long-term (12+ months)
- Cloud deployment option
- Multi-user with authentication
- Advanced backtesting
- Machine learning for strike selection
- Integration with additional brokers
