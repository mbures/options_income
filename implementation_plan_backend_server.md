# Implementation Plan: Wheel Strategy Backend Server

**Version:** 1.0
**Date:** 2026-01-31
**Status:** Draft

---

## Overview

This document outlines the phased implementation plan for migrating the wheel strategy tool to a backend server architecture with REST API and background task processing.

**Total Estimated Duration:** 12-14 weeks
**Approach:** Incremental delivery with backward compatibility
**Technology Stack:** FastAPI + APScheduler + SQLite + SQLAlchemy

---

## Phase 1: Backend Foundation (Weeks 1-2)

### Goals
- Set up FastAPI application structure
- Migrate database schema
- Implement core API endpoints
- Establish OpenAPI documentation

### Tasks

#### Sprint 1.1: Project Setup (3 days) ✅ COMPLETE
- [x] **S1.1.1**: Create `src/server/` directory structure
  - `main.py` (FastAPI app)
  - `api/` (endpoint routers)
  - `models/` (Pydantic request/response models)
  - `services/` (business logic layer)
  - `repositories/` (data access layer)
  - `config.py` (configuration management)
- [x] **S1.1.2**: Set up FastAPI application skeleton
  - Initialize FastAPI app
  - Configure CORS for local development
  - Add health check endpoint
  - Set up uvicorn server configuration
- [x] **S1.1.3**: Configure SQLAlchemy ORM
  - Database connection management
  - Session factory
  - Base model class
- [x] **S1.1.4**: Set up Alembic for migrations
  - Initialize Alembic
  - Configure migration environment
  - Create initial migration scripts
- [x] **S1.1.5**: Add development tools
  - pytest configuration
  - pytest-asyncio for async tests
  - Black/Pylint configuration (using existing project config)
  - Pre-commit hooks (using existing project hooks)

**Deliverables:** ✅ ALL COMPLETE
- ✅ Running FastAPI server at localhost:8000
- ✅ `/health` and `/api/v1/info` endpoints
- ✅ OpenAPI docs at `/docs`
- ✅ Test infrastructure (7 tests passing)

---

#### Sprint 1.2: Database Migration (4 days) ✅ COMPLETE
- [x] **S1.2.1**: Design new database schema
  - Add `portfolios` table
  - Enhance `wheels` table (add `portfolio_id`)
  - Keep `trades` table structure
  - Add `snapshots` table (renamed from position_snapshots)
  - Add `performance_metrics` table
  - Add `scheduler_config` table
- [x] **S1.2.2**: Create SQLAlchemy models
  - Portfolio model (src/server/database/models/portfolio.py)
  - Wheel model (enhanced - src/server/database/models/wheel.py)
  - Trade model (src/server/database/models/trade.py)
  - Snapshot model (src/server/database/models/snapshot.py)
  - PerformanceMetrics model (src/server/database/models/performance.py)
  - SchedulerConfig model (src/server/database/models/scheduler.py)
- [x] **S1.2.3**: Write migration script (old DB -> new DB)
  - Detect existing database
  - Create default portfolio automatically
  - Migrate wheels with portfolio association
  - Migrate position_snapshots → snapshots with wheel_id
  - Validate migration results (7-point validation)
  - Rollback capability with automatic backup
- [x] **S1.2.4**: Create database initialization script
  - Create fresh database (scripts/init_database.py)
  - Seed with default portfolio
  - Create indexes
  - Optional sample scheduler config
- [x] **S1.2.5**: Test migration with real data
  - Test on sample database (in-memory SQLite)
  - Migration scripts with --dry-run mode
  - Verify data integrity (22 model tests passing)

**Deliverables:** ✅ ALL COMPLETE
- ✅ New database schema (6 models, ~450 lines)
- ✅ Migration script (`scripts/migrate_database.py` with backup & validation)
- ✅ SQLAlchemy models (all with relationships & constraints)
- ✅ Migration tests (22 tests passing, 100% coverage)

---

#### Sprint 1.3: Portfolio & Wheel API (4 days) ✅ COMPLETE
- [x] **S1.3.1**: Create Pydantic request/response models
  - PortfolioCreate, PortfolioUpdate, PortfolioResponse, PortfolioSummary
  - WheelCreate, WheelUpdate, WheelResponse, WheelState
  - Comprehensive validation with Pydantic validators
- [x] **S1.3.2**: Implement PortfolioRepository
  - create_portfolio() - UUID generation, validation
  - get_portfolio() - Retrieve by ID
  - list_portfolios() - Pagination support
  - update_portfolio() - Partial updates
  - delete_portfolio() - Cascade to wheels
  - get_portfolio_summary() - Computed statistics
- [x] **S1.3.3**: Implement WheelRepository
  - create_wheel() - Portfolio validation, duplicate checking
  - get_wheel() - Retrieve by ID
  - list_wheels_by_portfolio() - Pagination, active filtering
  - update_wheel() - Partial updates
  - delete_wheel() - Cascade to trades/snapshots
  - get_wheel_state() - Current state with open trade
- [x] **S1.3.4**: Create API routers
  - `/api/v1/portfolios` - 6 endpoints (CRUD + summary + list)
  - `/api/v1/portfolios/{id}/wheels` - Create & list wheels
  - `/api/v1/wheels/{id}` - 4 endpoints (CRUD + state)
- [x] **S1.3.5**: Write integration tests
  - 17 portfolio tests (creation, CRUD, validation, cascade)
  - 23 wheel tests (creation, CRUD, validation, cascade, state)
  - All 40 tests passing

**Deliverables:** ✅ ALL COMPLETE
- ✅ Portfolio CRUD API (6 endpoints)
- ✅ Wheel CRUD API (6 endpoints)
- ✅ Repository layer (2 repositories, 12 methods each)
- ✅ Integration tests (40 tests passing, 100% success rate)
- ✅ Updated OpenAPI docs (Swagger UI at /docs)

---

## Phase 2: Business Logic Integration (Weeks 3-4)

### Goals
- Connect existing business logic to API
- Implement trade and recommendation endpoints
- Add position monitoring endpoints
- Maintain backward compatibility with existing code

### Tasks

#### Sprint 2.1: Trade Management API (3 days)
- [ ] **S2.1.1**: Create TradeRepository
  - Reuse/adapt existing WheelRepository trade methods
  - Add query methods (filter by date, outcome, etc.)
  - Add pagination support
- [ ] **S2.1.2**: Create Trade API endpoints
  - `POST /api/v1/wheels/{id}/trades` (record trade)
  - `GET /api/v1/wheels/{id}/trades` (list trades)
  - `GET /api/v1/trades/{id}` (get trade)
  - `PUT /api/v1/trades/{id}` (update)
  - `DELETE /api/v1/trades/{id}` (delete)
  - `POST /api/v1/trades/{id}/expire` (record expiration)
  - `POST /api/v1/trades/{id}/close` (close early)
- [ ] **S2.1.3**: Integrate WheelManager
  - Wrap WheelManager methods in API services
  - Handle state machine validation
  - Return appropriate error responses
- [ ] **S2.1.4**: Write integration tests
  - Test trade recording flow
  - Test expiration outcome
  - Test state transitions
  - Test validation errors

**Deliverables:**
- Trade API endpoints
- WheelManager integration
- Trade tests

---

#### Sprint 2.2: Recommendation API (3 days)
- [ ] **S2.2.1**: Create RecommendationService
  - Wrap RecommendEngine
  - Add caching for recommendations
  - Handle external API failures gracefully
- [ ] **S2.2.2**: Create Recommendation endpoints
  - `GET /api/v1/wheels/{id}/recommend`
  - `POST /api/v1/wheels/recommend/batch` (multiple symbols)
- [ ] **S2.2.3**: Add configuration for recommendation parameters
  - DTE preferences
  - Profile settings
  - Warning thresholds
- [ ] **S2.2.4**: Write tests
  - Test recommendation generation
  - Test with different profiles
  - Test warning detection
  - Test batch recommendations

**Deliverables:**
- Recommendation API
- RecommendEngine integration
- Tests

---

#### Sprint 2.3: Position Monitoring API (5 days)
- [ ] **S2.3.1**: Create PositionMonitorService
  - Wrap PositionMonitor class
  - Add caching for live position data
  - Batch price fetching optimization
- [ ] **S2.3.2**: Create Position endpoints
  - `GET /api/v1/wheels/{id}/position` (single position)
  - `GET /api/v1/portfolios/{id}/positions` (all in portfolio)
  - `GET /api/v1/positions/open` (all open positions)
  - `GET /api/v1/wheels/{id}/risk` (risk assessment)
- [ ] **S2.3.3**: Add query parameters
  - Filter by risk level
  - Filter by DTE range
  - Sort options
- [ ] **S2.3.4**: Write tests
  - Test position status calculation
  - Test moneyness calculation
  - Test risk assessment
  - Test batch position retrieval
  - Mock Schwab API calls

**Deliverables:**
- Position monitoring API
- PositionMonitor integration
- Tests

---

## Phase 3: Background Task System (Weeks 5-6)

### Goals
- Implement APScheduler integration
- Create core scheduled tasks
- Add task configuration and management
- Enable automated monitoring and snapshots

### Tasks

#### Sprint 3.1: Scheduler Setup (3 days)
- [ ] **S3.1.1**: Add APScheduler dependencies
  - apscheduler package
  - SQLAlchemy jobstore for persistence
- [ ] **S3.1.2**: Create SchedulerService
  - Initialize AsyncIOScheduler
  - Configure jobstore
  - Startup/shutdown lifecycle hooks
- [ ] **S3.1.3**: Integrate with FastAPI app
  - Add startup event to start scheduler
  - Add shutdown event to stop scheduler
  - Health check includes scheduler status
- [ ] **S3.1.4**: Create SchedulerConfigRepository
  - CRUD for task configurations
  - Load configs on startup
  - Apply configs to running scheduler
- [ ] **S3.1.5**: Write tests
  - Test scheduler lifecycle
  - Test job persistence
  - Test config loading

**Deliverables:**
- APScheduler integrated
- Scheduler lifecycle management
- Configuration persistence
- Tests

---

#### Sprint 3.2: Core Scheduled Tasks (5 days)
- [ ] **S3.2.1**: Implement Price Refresh Task
  - Get all open positions
  - Batch fetch prices (limit API calls)
  - Update position cache
  - Log failures
  - Default: Every 5 minutes
- [ ] **S3.2.2**: Implement Daily Snapshot Task
  - Get all open positions at EOD
  - Create snapshot for each
  - Store in database
  - Default: 4:30 PM ET daily
- [ ] **S3.2.3**: Implement Risk Monitoring Task
  - Check all positions for high risk
  - Flag ITM positions
  - Flag near-expiration (< 3 DTE)
  - Log warnings
  - Default: Every 15 minutes
- [ ] **S3.2.4**: Implement Opportunity Scanning Task
  - Get tracked symbols (from config or portfolios)
  - Generate recommendations
  - Filter for favorable setups (optional)
  - Log opportunities
  - Default: Daily at 9:45 AM ET
- [ ] **S3.2.5**: Add market hours awareness
  - Define market hours (configurable)
  - Pause/resume tasks based on market state
  - Use trading calendar for holidays
- [ ] **S3.2.6**: Write tests
  - Test each task execution
  - Test market hours logic
  - Test error handling
  - Test task scheduling

**Deliverables:**
- 4 core scheduled tasks
- Market hours logic
- Task execution tests

---

#### Sprint 3.3: Scheduler Management API (3 days)
- [ ] **S3.3.1**: Create Scheduler API endpoints
  - `GET /api/v1/scheduler/jobs` (list jobs)
  - `GET /api/v1/scheduler/jobs/{id}` (job details)
  - `PUT /api/v1/scheduler/jobs/{id}` (update schedule)
  - `POST /api/v1/scheduler/jobs/{id}/trigger` (manual trigger)
  - `GET /api/v1/scheduler/history` (execution history)
- [ ] **S3.3.2**: Add job execution logging
  - Log start/end time
  - Log success/failure
  - Log execution duration
  - Store in database
- [ ] **S3.3.3**: Create UI-friendly job models
  - Next run time
  - Last run time
  - Success/failure status
  - Human-readable schedule
- [ ] **S3.3.4**: Write tests
  - Test job listing
  - Test schedule updates
  - Test manual triggering
  - Test history retrieval

**Deliverables:**
- Scheduler management API
- Job execution logging
- Tests

---

## Phase 4: Plugin System (Weeks 7-8)

### Goals
- Create plugin framework
- Enable dynamic task registration
- Provide example plugins
- Document plugin development

### Tasks

#### Sprint 4.1: Plugin Framework (4 days)
- [ ] **S4.1.1**: Design plugin base class
  - Abstract methods: name, default_schedule, execute
  - Optional hooks: on_success, on_failure, on_startup
  - Context access (db session, services, config)
- [ ] **S4.1.2**: Create PluginManager
  - Register plugins
  - Discover plugins from directory
  - Add to scheduler on registration
  - Enable/disable plugins
  - Unregister plugins
- [ ] **S4.1.3**: Add plugin configuration
  - Store enabled plugins in database
  - Store custom schedules
  - Persist plugin state
- [ ] **S4.1.4**: Create plugin loading system
  - Scan `plugins/` directory
  - Import plugin modules
  - Validate plugin implementations
  - Handle import errors gracefully
- [ ] **S4.1.5**: Write tests
  - Test plugin discovery
  - Test plugin registration
  - Test plugin execution
  - Test error handling

**Deliverables:**
- Plugin base class
- PluginManager
- Plugin discovery
- Tests

---

#### Sprint 4.2: Example Plugins & API (4 days)
- [ ] **S4.2.1**: Create example plugins
  - **Earnings Alert Plugin**: Alert when earnings within 7 days
  - **Volatility Spike Plugin**: Alert on unusual IV changes
  - **Premium Target Plugin**: Track cumulative premium goals
- [ ] **S4.2.2**: Create Plugin API endpoints
  - `GET /api/v1/plugins` (list registered)
  - `GET /api/v1/plugins/{name}` (details)
  - `POST /api/v1/plugins/{name}/enable` (enable)
  - `POST /api/v1/plugins/{name}/disable` (disable)
  - `PUT /api/v1/plugins/{name}/schedule` (update)
- [ ] **S4.2.3**: Document plugin development
  - Plugin development guide
  - API reference
  - Example plugin walkthrough
  - Best practices
- [ ] **S4.2.4**: Write tests
  - Test example plugins
  - Test plugin API
  - Test custom plugin scenarios

**Deliverables:**
- 3 example plugins
- Plugin management API
- Plugin development guide
- Tests

---

## Phase 5: CLI Migration (Weeks 9-10)

### Goals
- Convert CLI to API client
- Maintain command compatibility
- Add portfolio selection
- Remove direct database access

### Tasks

#### Sprint 5.1: API Client Library (3 days)
- [ ] **S5.1.1**: Create WheelStrategyAPIClient class
  - HTTP client (httpx)
  - All API endpoints wrapped
  - Error handling
  - Timeout configuration
- [ ] **S5.1.2**: Add configuration file support
  - Read from `~/.wheel_strategy/config.yaml`
  - API endpoint URL
  - Default portfolio
  - Timeout settings
- [ ] **S5.1.3**: Add connection detection
  - Check if API server is reachable
  - Fall back to direct mode if API unavailable
  - Warn user about mode
- [ ] **S5.1.4**: Write tests
  - Test API client methods
  - Test error handling
  - Test fallback logic
  - Mock HTTP responses

**Deliverables:**
- API client library
- Configuration file support
- Tests

---

#### Sprint 5.2: CLI Refactoring (5 days)
- [ ] **S5.2.1**: Refactor `wheel init` command
  - Add `--portfolio` flag
  - Call API client instead of WheelManager
  - Maintain output format
- [ ] **S5.2.2**: Refactor `wheel record` command
  - Call API client
  - Handle API errors
  - Same output format
- [ ] **S5.2.3**: Refactor `wheel list` command
  - Call API client
  - Add portfolio filter
  - Same table format
- [ ] **S5.2.4**: Refactor `wheel expire` command
  - Call API client
  - Handle state updates
- [ ] **S5.2.5**: Refactor `wheel status` command
  - Call position monitoring API
  - Enhanced with live data
- [ ] **S5.2.6**: Refactor `wheel performance` command
  - Call performance API
  - Add date range filters
- [ ] **S5.2.7**: Refactor `wheel recommend` command
  - Call recommendation API
  - Same output format
- [ ] **S5.2.8**: Add portfolio management commands
  - `wheel portfolio create`
  - `wheel portfolio list`
  - `wheel portfolio set-default`
- [ ] **S5.2.9**: Update help text and docs
  - Update command help
  - Update README
  - Migration guide
- [ ] **S5.2.10**: Write tests
  - Test all commands in API mode
  - Test fallback to direct mode
  - Test portfolio commands
  - Compare output with old version

**Deliverables:**
- Refactored CLI (API mode)
- Portfolio commands
- Updated documentation
- Tests

---

## Phase 6: Performance Analytics (Weeks 11-12)

### Goals
- Implement performance calculation
- Add historical analytics
- Create trend analysis
- Enable data export

### Tasks

#### Sprint 6.1: Performance Calculation (4 days)
- [ ] **S6.1.1**: Create PerformanceService
  - Calculate wheel-level metrics
  - Calculate portfolio-level metrics
  - Calculate system-wide metrics
  - Support date range filtering
- [ ] **S6.1.2**: Implement PerformanceRepository
  - Store pre-calculated metrics
  - Query by time period
  - Aggregate across wheels/portfolios
- [ ] **S6.1.3**: Create scheduled task for metric calculation
  - Run nightly
  - Calculate daily/weekly/monthly metrics
  - Store in performance_metrics table
- [ ] **S6.1.4**: Write tests
  - Test metric calculations
  - Test aggregations
  - Test edge cases (no trades, etc.)

**Deliverables:**
- Performance calculation service
- Nightly metric calculation
- Tests

---

#### Sprint 6.2: Analytics API (4 days)
- [ ] **S6.2.1**: Create Performance endpoints
  - `GET /api/v1/wheels/{id}/performance`
  - `GET /api/v1/portfolios/{id}/performance`
  - `GET /api/v1/performance/aggregate`
  - `GET /api/v1/performance/win-loss`
  - Query params: start_date, end_date, period
- [ ] **S6.2.2**: Create Snapshot endpoints
  - `GET /api/v1/wheels/{id}/snapshots`
  - `GET /api/v1/wheels/{id}/snapshots/latest`
  - `POST /api/v1/wheels/{id}/snapshots` (manual)
- [ ] **S6.2.3**: Create Trend endpoint
  - `GET /api/v1/wheels/{id}/trend`
  - Return time series data
  - Support different intervals (daily, weekly)
- [ ] **S6.2.4**: Create Export endpoint
  - `GET /api/v1/performance/export?format=csv`
  - Export trades
  - Export performance metrics
  - Export snapshots
- [ ] **S6.2.5**: Write tests
  - Test all endpoints
  - Test date filtering
  - Test CSV export format

**Deliverables:**
- Performance API
- Export functionality
- Tests

---

#### Sprint 6.3: CLI Analytics Commands (3 days)
- [ ] **S6.3.1**: Add `wheel analytics` command
  - Show win/loss ratio
  - Show P&L over time
  - Show best/worst performers
- [ ] **S6.3.2**: Add `wheel export` command
  - Export to CSV
  - Support filtering
- [ ] **S6.3.3**: Update `wheel status` for trends
  - Show recent snapshots
  - Show price trend
- [ ] **S6.3.4**: Write tests
  - Test new commands
  - Test output formatting

**Deliverables:**
- Analytics CLI commands
- Tests

---

## Phase 7: Documentation & Polish (Week 13)

### Goals
- Comprehensive documentation
- User and developer guides
- Deployment instructions
- Final testing and bug fixes

### Tasks

#### Sprint 7.1: Documentation (4 days)
- [ ] **S7.1.1**: Update README
  - Architecture overview
  - Quick start guide
  - Installation instructions
- [ ] **S7.1.2**: Write User Guide
  - Server setup
  - Configuration
  - CLI usage (API mode)
  - Portfolio management
  - Background tasks
- [ ] **S7.1.3**: Write Migration Guide
  - Prerequisites
  - Backup instructions
  - Migration steps
  - Verification
  - Rollback procedure
- [ ] **S7.1.4**: Write Developer Guide
  - Architecture overview
  - API development
  - Plugin development
  - Testing
  - Contributing
- [ ] **S7.1.5**: Write Deployment Guide
  - systemd service setup
  - Configuration options
  - Monitoring
  - Troubleshooting

**Deliverables:**
- Updated README
- User guide
- Migration guide
- Developer guide
- Deployment guide

---

#### Sprint 7.2: Testing & Polish (3 days)
- [ ] **S7.2.1**: End-to-end testing
  - Test full user workflows
  - Test migration path
  - Test API + CLI together
  - Performance testing
- [ ] **S7.2.2**: Bug fixes
  - Address any issues found
  - Code cleanup
  - Error message improvements
- [ ] **S7.2.3**: Performance optimization
  - Query optimization
  - Caching tuning
  - API response time checks
- [ ] **S7.2.4**: Final review
  - Code review
  - Documentation review
  - OpenAPI spec validation

**Deliverables:**
- Bug fixes
- Performance improvements
- Production-ready system

---

## Checkpoints and Reviews

### Checkpoint 1 (End of Phase 1)
**Review:**
- API structure and design
- Database migration strategy
- OpenAPI documentation quality

**Decision Point:** Proceed to Phase 2 or adjust API design

---

### Checkpoint 2 (End of Phase 2)
**Review:**
- Business logic integration
- API completeness
- Backward compatibility

**Decision Point:** Proceed to Phase 3 or address gaps

---

### Checkpoint 3 (End of Phase 3)
**Review:**
- Background task reliability
- Scheduler stability
- Resource usage

**Decision Point:** Proceed to Phase 4 or refine tasks

---

### Checkpoint 4 (End of Phase 5)
**Review:**
- CLI migration success
- User acceptance testing
- Command compatibility

**Decision Point:** Soft launch or continue development

---

### Final Review (End of Phase 7)
**Review:**
- System stability
- Documentation completeness
- User readiness

**Decision Point:** Production release or additional polish

---

## Risk Management

### Technical Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Database migration failure | High | Backup required, validation tests, rollback plan |
| APScheduler instability | Medium | Extensive testing, fallback to manual triggers |
| API performance issues | Medium | Load testing, caching, query optimization |
| CLI compatibility breaks | High | Automated tests, side-by-side comparison |

### Schedule Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Phase delays | Medium | Buffer time in schedule, parallel work when possible |
| Scope creep | High | Strict phase boundaries, defer enhancements to future |
| Testing time underestimated | Medium | Continuous testing throughout, dedicated test phase |

---

## Success Criteria

### Phase 1 Success
- [ ] API server runs and responds to requests
- [ ] Database migration completes without errors
- [ ] OpenAPI docs generated correctly
- [ ] Tests pass (>80% coverage)

### Phase 2 Success
- [ ] All core endpoints implemented
- [ ] Existing business logic integrated
- [ ] API mode CLI flag works
- [ ] No regression in functionality

### Phase 3 Success
- [ ] Scheduler runs reliably
- [ ] All 4 core tasks execute
- [ ] Task configuration persists
- [ ] No performance degradation

### Phase 4 Success
- [ ] Plugin system works
- [ ] Example plugins functional
- [ ] Plugin API operational
- [ ] Documentation complete

### Phase 5 Success
- [ ] CLI fully migrated to API
- [ ] All commands work identically
- [ ] Portfolio management works
- [ ] Users can migrate seamlessly

### Phase 6 Success
- [ ] Performance metrics accurate
- [ ] Analytics provide insights
- [ ] Export functionality works
- [ ] Historical data accessible

### Phase 7 Success
- [ ] Documentation complete and clear
- [ ] System stable and tested
- [ ] User acceptance achieved
- [ ] Ready for production use

---

## Post-Launch Plan

### Week 14-15: Stabilization
- Monitor logs for errors
- Address user-reported issues
- Performance tuning
- Documentation updates

### Week 16+: Enhancements
- Web UI development
- Additional plugins
- Enhanced analytics
- Community feedback integration
