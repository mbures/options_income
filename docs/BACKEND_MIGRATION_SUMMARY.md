# Backend Migration Summary

**Date:** 2026-01-31
**Status:** Planning Complete, Ready for Implementation

---

## Overview

This document summarizes the plan to migrate the wheel strategy tool from a CLI-only application to a backend server architecture with REST API and automated background processing.

---

## Architecture Decision

**Technology Stack:**
- **FastAPI**: Modern async web framework with built-in OpenAPI support
- **APScheduler**: Asyncio-based job scheduling for background tasks
- **SQLite**: Embedded database (no changes for single-user deployment)
- **SQLAlchemy**: ORM for data access layer
- **Uvicorn**: ASGI server

**Key Benefits:**
- Lightweight (no Redis/RabbitMQ required)
- Native asyncio integration
- Auto-generated OpenAPI documentation
- Simple deployment (single process)
- Easy plugin development

---

## Documents Created

### 1. System Design Document
**File:** `docs/design_backend_server.md`

**Contents:**
- High-level architecture diagrams
- Component responsibilities
- REST API structure (all endpoints)
- Background task system design
- Plugin framework architecture
- Database schema (enhanced)
- Technology stack details
- Deployment architecture
- Security considerations
- Migration strategy (7 phases)

**Key Sections:**
- 12 sections covering all aspects
- Complete API endpoint reference
- Request/response examples
- Background task specifications
- Plugin system design

---

### 2. Product Requirements Document
**File:** `docs/prd_backend_server.md`

**Contents:**
- Product overview and goals
- User stories (13 stories)
- Functional requirements (33 FRs)
- Non-functional requirements (14 NFRs)
- API specification details
- Data models (Pydantic schemas)
- Migration strategy
- Configuration management
- Success metrics
- Risk mitigation

**Key Features:**
- Multi-portfolio support
- Automated background tasks
- Real-time position monitoring
- Historical analytics
- Plugin system for extensibility
- OpenAPI documentation
- Backward-compatible CLI

---

### 3. Implementation Plan
**File:** `docs/implementation_plan_backend_server.md`

**Contents:**
- 7 implementation phases
- 13 sprints with detailed tasks
- Timeline (12-14 weeks total)
- Checkpoint reviews
- Risk management
- Success criteria per phase
- Post-launch plan

**Phases:**
1. **Backend Foundation** (Weeks 1-2): FastAPI setup, DB migration, core API
2. **Business Logic Integration** (Weeks 3-4): Connect existing code, recommendations, monitoring
3. **Background Task System** (Weeks 5-6): APScheduler, core tasks, market hours
4. **Plugin System** (Weeks 7-8): Plugin framework, examples, API
5. **CLI Migration** (Weeks 9-10): Refactor CLI to API client
6. **Performance Analytics** (Weeks 11-12): Metrics, trends, export
7. **Documentation & Polish** (Week 13): Guides, testing, final review

---

## Key Architectural Changes

### Current State
```
CLI → WheelManager → WheelRepository → SQLite
```

### Future State
```
┌─────────────────┐
│  CLI Client     │  (Uses API)
│  Web Client     │  (Future)
│  Mobile Client  │  (Future)
└────────┬────────┘
         ↓ HTTP/REST
┌─────────────────────────────────┐
│  FastAPI Server                  │
│  ┌──────────────────────────┐  │
│  │  REST API Endpoints       │  │
│  └──────────────────────────┘  │
│  ┌──────────────────────────┐  │
│  │  Background Tasks         │  │
│  │  (APScheduler)            │  │
│  └──────────────────────────┘  │
│  ┌──────────────────────────┐  │
│  │  Business Logic           │  │
│  │  (WheelManager, etc.)     │  │
│  └──────────────────────────┘  │
│  ┌──────────────────────────┐  │
│  │  Repository Layer         │  │
│  │  (SQLAlchemy)             │  │
│  └──────────────────────────┘  │
└─────────────────────────────────┘
         ↓
┌─────────────────┐
│  SQLite DB      │
│  (Enhanced)     │
└─────────────────┘
```

---

## New Features

### 1. Multi-Portfolio Support
- Organize wheels by portfolio (e.g., "Primary", "Experimental", "IRA")
- Independent tracking and performance
- Portfolio-level aggregation

### 2. Automated Background Tasks

**Price Refresh:**
- Auto-update prices every 5 minutes
- Configurable interval
- Market hours aware

**Daily Snapshots:**
- Capture EOD position state
- Historical trend analysis
- Automated at 4:30 PM ET

**Risk Monitoring:**
- Check for ITM positions
- Flag near-expiration risks
- Alert on high-risk conditions

**Opportunity Scanning:**
- Scan tracked symbols
- Generate recommendations
- Identify favorable setups

### 3. REST API
- All operations available via HTTP
- OpenAPI documentation
- Swagger UI for testing
- Standardized error responses

### 4. Plugin System
- Custom scheduled tasks
- Plugin base class
- Dynamic registration
- Configuration per plugin

### 5. Enhanced Analytics
- Win/loss tracking
- Performance over time
- Best/worst performers
- CSV export

---

## API Endpoints Summary

**Portfolios:** 6 endpoints (CRUD + summary)
**Wheels:** 6 endpoints (CRUD + state)
**Trades:** 7 endpoints (CRUD + expire + close)
**Recommendations:** 2 endpoints (single + batch)
**Positions:** 4 endpoints (monitoring + risk)
**Snapshots:** 3 endpoints (list + latest + create)
**Performance:** 5 endpoints (wheel + portfolio + aggregate + export)
**Scheduler:** 5 endpoints (jobs + history + trigger)
**System:** 3 endpoints (health + info + config)

**Total:** ~40 endpoints

---

## Database Changes

### New Tables
- `portfolios`: Portfolio management
- `performance_metrics`: Pre-calculated performance data
- `scheduler_config`: Task configuration
- `snapshots`: Enhanced with more fields

### Enhanced Tables
- `wheels`: Add `portfolio_id` foreign key
- Keep `trades` unchanged for compatibility

### Migration Strategy
- Automated migration script
- Create default portfolio
- Associate existing wheels with default portfolio
- Preserve all trade history
- Validation and rollback capability

---

## Deployment Model

### Development
```bash
# Terminal 1: Start backend server
cd /workspaces/options_income
uvicorn src.server.main:app --reload --port 8000

# Terminal 2: Use CLI in API mode
export WHEEL_STRATEGY_API=http://localhost:8000
python wheel_strategy_tool.py list
```

### Production (systemd service)
```bash
# Install and enable service
sudo cp wheel-strategy-server.service /etc/systemd/system/
sudo systemctl enable wheel-strategy-server
sudo systemctl start wheel-strategy-server

# CLI automatically uses local API
python wheel_strategy_tool.py list
```

---

## Configuration Files

### Server Config
**File:** `config/server.yaml`
```yaml
server:
  host: "0.0.0.0"
  port: 8000

scheduler:
  enabled: true
  market_hours:
    open: "09:30"
    close: "16:00"
    timezone: "America/New_York"

tasks:
  price_refresh:
    enabled: true
    interval: 300  # 5 minutes
  daily_snapshot:
    enabled: true
    time: "16:30"
```

### CLI Config
**File:** `~/.wheel_strategy/config.yaml`
```yaml
api:
  enabled: true
  base_url: "http://localhost:8000"

default_portfolio: "primary"
```

---

## Migration Path for Users

### Step 1: Backup
```bash
# Backup current database
cp ~/.wheel_strategy/wheels.db ~/.wheel_strategy/wheels.db.backup
```

### Step 2: Install & Migrate
```bash
# Update to new version
git pull
pip install -r requirements.txt

# Run migration
python scripts/migrate_database.py
```

### Step 3: Start Server
```bash
# Start server (or enable systemd service)
uvicorn src.server.main:app --host 0.0.0.0 --port 8000
```

### Step 4: Configure CLI
```bash
# Update CLI config to use API
echo "api:\n  enabled: true\n  base_url: http://localhost:8000" > ~/.wheel_strategy/config.yaml
```

### Step 5: Verify
```bash
# Test CLI commands
python wheel_strategy_tool.py list
python wheel_strategy_tool.py status AAPL

# Check API docs
open http://localhost:8000/docs
```

---

## Timeline Summary

| Phase | Duration | Key Deliverables |
|-------|----------|------------------|
| Phase 1 | 2 weeks | API foundation, DB migration, core endpoints |
| Phase 2 | 2 weeks | Business logic integration, recommendations, monitoring |
| Phase 3 | 2 weeks | Background tasks, APScheduler, core automation |
| Phase 4 | 2 weeks | Plugin system, examples, extensibility |
| Phase 5 | 2 weeks | CLI migration to API client |
| Phase 6 | 2 weeks | Performance analytics, trends, export |
| Phase 7 | 1 week | Documentation, testing, polish |

**Total:** 13 weeks (approximately 3 months)

---

## Success Metrics

### Technical Metrics
- [ ] API response time < 200ms (95th percentile)
- [ ] Background task success rate > 99%
- [ ] Zero data loss during migration
- [ ] Test coverage > 80%
- [ ] All existing CLI commands work identically

### User Experience Metrics
- [ ] Migration takes < 1 hour
- [ ] CLI feels unchanged to users
- [ ] Background tasks "just work"
- [ ] Portfolio organization useful
- [ ] Documentation clear and helpful

### Business Metrics
- [ ] Reduced manual monitoring time
- [ ] Faster opportunity identification
- [ ] Better risk awareness
- [ ] Improved performance tracking
- [ ] Foundation for future UI development

---

## Next Steps

### Immediate (This Week)
1. **Review documents** with stakeholders
2. **Finalize phase 1 scope** and tasks
3. **Set up project structure** (`src/server/` directory)
4. **Create development branch** (`feature/backend-server`)

### Phase 1 Start (Next Week)
1. **Sprint 1.1**: Project setup (3 days)
   - FastAPI skeleton
   - SQLAlchemy configuration
   - Test infrastructure
2. **Sprint 1.2**: Database migration (4 days)
   - New schema design
   - Migration script
   - Testing with real data
3. **Sprint 1.3**: Core API (4 days)
   - Portfolio endpoints
   - Wheel endpoints
   - OpenAPI docs

### Ongoing
- Daily standups (track progress)
- Weekly demos (show working features)
- Checkpoint reviews (end of each phase)
- Documentation updates (as we build)

---

## Questions and Decisions

### Resolved
- ✅ Technology stack: FastAPI + APScheduler
- ✅ Database: Keep SQLite
- ✅ Authentication: Single-user, no auth for now
- ✅ Deployment: Local/LAN network
- ✅ Migration approach: Phased with backward compatibility

### Pending
- ⏳ Exact market hours (configurable, but defaults?)
- ⏳ Plugin directory location (`plugins/` in project root?)
- ⏳ Log file locations (`logs/` or `/var/log/`?)
- ⏳ systemd service name (`wheel-strategy-server`?)

---

## Resources

### Documentation
- **System Design:** `docs/design_backend_server.md`
- **Requirements:** `docs/prd_backend_server.md`
- **Implementation Plan:** `docs/implementation_plan_backend_server.md`
- **This Summary:** `docs/BACKEND_MIGRATION_SUMMARY.md`

### Technology References
- FastAPI: https://fastapi.tiangolo.com/
- APScheduler: https://apscheduler.readthedocs.io/
- SQLAlchemy: https://docs.sqlalchemy.org/
- Pydantic: https://docs.pydantic.dev/

### Internal References
- Current design: `docs/design_wheel_strategy_tool.md`
- Current PRD: `docs/prd_wheel_strategy_tool.md`
- Schwab OAuth setup: `docs/SCHWAB_OAUTH_SETUP.md`

---

## Conclusion

This backend migration will transform the wheel strategy tool from a simple CLI application into a robust, extensible platform that:

1. **Automates** routine monitoring and data collection
2. **Enables** future client development (web, mobile)
3. **Organizes** trading with multi-portfolio support
4. **Provides** rich analytics and performance tracking
5. **Extends** easily via plugin system

The phased approach ensures:
- Backward compatibility during migration
- Incremental value delivery
- Risk mitigation through checkpoints
- Smooth user transition

**We're ready to begin Phase 1!**
