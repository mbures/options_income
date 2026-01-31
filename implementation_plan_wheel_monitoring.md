# Implementation Plan: Wheel Strategy Position Monitoring

## Overview

This plan details the implementation steps for adding position monitoring capabilities to the Wheel Strategy Tool. The enhancement provides real-time status tracking for open positions, including DTE, moneyness, risk assessment, and historical snapshots.

## Stakeholder Decisions

| Decision Area | Requirement |
|--------------|-------------|
| DTE Display | Both calendar and trading days: "14 days (10 trading days)" |
| Refresh Timing | On startup + hourly during market + once after hours |
| ATM Threshold | Strict: ITM = any intrinsic value |
| Risk Indicators | HIGH = any ITM, MEDIUM = OTM 0-5%, LOW = OTM >5% |
| List Display | Full details with all monitoring stats |
| Historical Tracking | Daily snapshots saved to database |

## Architecture Separation

### Backing Library (src/wheel/)

New or modified files that provide core functionality:
- `monitor.py` (NEW): PositionMonitor service
- `models.py` (MODIFY): Add PositionStatus and PositionSnapshot dataclasses
- `manager.py` (MODIFY): Add monitoring methods
- `repository.py` (MODIFY): Add snapshot persistence
- `__init__.py` (MODIFY): Export new classes

### Application Layer

Files that handle user interface and presentation:
- `cli.py` (MODIFY): Enhance status, list commands; add refresh command
- `wheel_strategy_tool.py` (MODIFY): Export new model classes

### No Changes Needed

Existing infrastructure to leverage:
- Price fetching: SchwabClient, AlphaVantagePriceDataFetcher
- DTE calculation: calculate_days_to_expiry utility
- Caching: 5-minute TTL on quotes
- Trading day calculation: calculate_trading_days utility (may need to create)

## Implementation Tasks

### Phase 1: Data Models and Database

**Task 1.1: Add PositionStatus model**
- Location: `src/wheel/models.py`
- Fields: symbol, direction, strike, expiration_date, dte_calendar, dte_trading, current_price, price_vs_strike, is_itm, is_otm, moneyness_pct, moneyness_label, risk_level, risk_icon, last_updated, premium_collected
- Add computed property: risk_description

**Task 1.2: Add PositionSnapshot model**
- Location: `src/wheel/models.py`
- Fields: id, trade_id, snapshot_date, current_price, dte_calendar, dte_trading, moneyness_pct, is_itm, risk_level, created_at

**Task 1.3: Update WheelPosition model**
- Location: `src/wheel/models.py`
- Add computed property: has_monitorable_position
- Returns True if state is CASH_PUT_OPEN or SHARES_CALL_OPEN

**Task 1.4: Add position_snapshots table to database**
- Location: `src/wheel/repository.py` - _init_database method
- Columns: id, trade_id, snapshot_date, current_price, dte_calendar, dte_trading, moneyness_pct, is_itm, risk_level, created_at
- Add indexes on trade_id and snapshot_date
- Add unique constraint on (trade_id, snapshot_date)

### Phase 2: Core Monitoring Logic

**Task 2.1: Create PositionMonitor class**
- Location: `src/wheel/monitor.py` (NEW FILE)
- Initialize with schwab_client and price_fetcher
- Set up internal cache dictionary

**Task 2.2: Implement _fetch_current_price method**
- Check internal cache first (respect 5-minute TTL)
- Use SchwabClient as primary data source
- Fall back to AlphaVantagePriceDataFetcher
- Update cache on successful fetch
- Handle errors gracefully

**Task 2.3: Implement _calculate_moneyness method**
- Create MoneynessResult helper dataclass
- For puts: ITM when current_price <= strike
- For calls: ITM when current_price >= strike
- Calculate percentage distance: (current_price - strike) / strike * 100
- Generate human-readable label: "OTM by X.X%" or "ITM by X.X%"
- Calculate price_diff (signed distance from strike)

**Task 2.4: Implement _assess_risk method**
- HIGH (🔴): is_itm = True
- MEDIUM (🟡): is_otm = True AND abs(moneyness_pct) <= 5.0
- LOW (🟢): is_otm = True AND abs(moneyness_pct) > 5.0
- Return tuple of (risk_level, risk_icon)

**Task 2.5: Implement get_position_status method**
- Validate position is in monitorable state
- Fetch current price (respect cache unless force_refresh)
- Calculate DTE (calendar days using calculate_days_to_expiry)
- Calculate trading days (using calculate_trading_days or create if needed)
- Calculate moneyness using _calculate_moneyness
- Assess risk using _assess_risk
- Construct and return PositionStatus object

**Task 2.6: Implement get_all_positions_status method**
- Filter for monitorable positions only
- Find open trade for each position
- Call get_position_status for each
- Handle errors per-position (log warning, continue with others)
- Return list of tuples: (WheelPosition, TradeRecord, PositionStatus)

**Task 2.7: Implement create_snapshot method**
- Accept trade and status objects
- Extract snapshot data from status
- Create PositionSnapshot instance
- Return snapshot for persistence

**Task 2.8: Implement _find_open_trade helper**
- Search trades list for matching wheel_id and OPEN outcome
- Return first match or None

### Phase 3: Repository Integration

**Task 3.1: Implement create_snapshot in repository**
- Location: `src/wheel/repository.py`
- Insert snapshot into position_snapshots table
- Handle unique constraint violation gracefully
- Return snapshot with assigned id

**Task 3.2: Implement get_snapshots in repository**
- Accept trade_id, optional start_date, optional end_date
- Query snapshots with date range filtering
- Order by snapshot_date ascending
- Return list of PositionSnapshot objects

**Task 3.3: Implement has_snapshots_for_date in repository**
- Accept snapshot_date
- Query count of snapshots for that date
- Return boolean (count > 0)

**Task 3.4: Implement _row_to_snapshot helper**
- Convert database row dict to PositionSnapshot object
- Handle type conversions (int for is_itm boolean, datetime parsing)

### Phase 4: Manager Integration

**Task 4.1: Add PositionMonitor to WheelManager.__init__**
- Instantiate PositionMonitor with schwab_client and price_fetcher
- Store as self.monitor

**Task 4.2: Implement get_position_status in manager**
- Accept symbol and force_refresh flag
- Get wheel position from repository
- Check if has_monitorable_position
- Get open trade from repository
- Delegate to monitor.get_position_status
- Return PositionStatus or None

**Task 4.3: Implement get_all_positions_status in manager**
- Get all active wheels from repository
- Get all open trades from repository
- Delegate to monitor.get_all_positions_status
- Return list of tuples

**Task 4.4: Implement refresh_snapshots in manager**
- Check if snapshots exist for today (unless force=True)
- Get all open positions status with force_refresh=True
- For each position: create snapshot, save to repository
- Return count of snapshots created

### Phase 5: CLI Enhancements

**Task 5.1: Enhance status command**
- Add --refresh flag
- Call manager.get_position_status
- Update _print_status helper to include monitoring data
- Display: current price, DTE (both formats), moneyness, risk level
- Add HIGH risk warning section
- Show timestamp of last update

**Task 5.2: Enhance list command**
- Add --refresh flag
- Call manager.get_all_positions_status
- Update table headers: Symbol, State, Strike, Current, DTE, Moneyness, Risk
- Map status data for each wheel
- Show placeholders for closed positions
- Add summary line with HIGH risk count

**Task 5.3: Create refresh command**
- Call manager.refresh_snapshots
- Display count of snapshots created
- Show "already up-to-date" message if count = 0
- Provide guidance on cron setup

**Task 5.4: Add helper function _format_dte**
- Accept dte_calendar and dte_trading
- Return formatted string: "14 days (10 trading days)"

**Task 5.5: Add helper function _print_status_with_monitoring**
- Accept position, trade, status, verbose flag
- Print position basics
- Print open trade details
- Print live monitoring data section
- Add HIGH risk warning box if applicable

### Phase 6: Utility Functions

**Task 6.1: Create or verify calculate_trading_days**
- Location: Check if exists in src/utils.py, create if needed
- Accept start_date and end_date
- Count weekdays between dates
- Exclude market holidays (NYSE calendar)
- Return integer count

**Task 6.2: Verify calculate_days_to_expiry exists**
- Location: Should exist in existing codebase
- If not, create utility to calculate calendar days until expiration

### Phase 7: Module Exports

**Task 7.1: Update src/wheel/__init__.py**
- Export PositionMonitor
- Export PositionStatus
- Export PositionSnapshot
- Add to __all__ list

**Task 7.2: Update wheel_strategy_tool.py**
- Import PositionStatus and PositionSnapshot
- Export in __all__ list
- Update module docstring to mention monitoring

### Phase 8: Testing

**Task 8.1: Create test_monitor.py**
- Test moneyness calculation (puts ITM/OTM)
- Test moneyness calculation (calls ITM/OTM)
- Test risk assessment (all three levels)
- Test DTE calculation
- Test cache behavior
- Test force refresh
- Test error handling

**Task 8.2: Create test_repository_snapshots.py**
- Test snapshot creation
- Test snapshot retrieval by trade_id
- Test snapshot retrieval with date range
- Test has_snapshots_for_date
- Test unique constraint enforcement
- Test _row_to_snapshot conversion

**Task 8.3: Update test_manager.py**
- Test get_position_status
- Test get_all_positions_status
- Test refresh_snapshots
- Test behavior when no open positions

**Task 8.4: Update test_cli.py**
- Test status command with --refresh
- Test list command with monitoring data
- Test refresh command
- Test HIGH risk warning display

**Task 8.5: Integration tests**
- Test end-to-end: create wheel → record trade → check status
- Test multiple positions with different risk levels
- Test daily snapshot workflow
- Test cache timing behavior

### Phase 9: Documentation

**Task 9.1: Update user documentation**
- Add section on position monitoring to README or user guide
- Document --refresh flag usage
- Provide cron job examples for daily snapshots
- Explain risk levels and what they mean

**Task 9.2: Update API documentation**
- Document PositionStatus dataclass
- Document PositionSnapshot dataclass
- Document new manager methods
- Provide usage examples

**Task 9.3: Add inline documentation**
- Docstrings for all new classes and methods
- Explain moneyness calculation logic
- Explain risk assessment thresholds
- Document cache behavior

## Dependencies

### External Libraries
- No new external libraries required
- Uses existing: sqlite3, datetime, dataclasses

### Existing Codebase Components
- SchwabClient: For price quotes
- AlphaVantagePriceDataFetcher: Fallback for prices
- calculate_days_to_expiry: For DTE calculation
- WheelPosition, TradeRecord: Existing models
- WheelRepository: For database operations

### New Utilities (if needed)
- calculate_trading_days: May need to create if doesn't exist
- Market holiday calendar: For accurate trading day calculation

## Risk Mitigation

### API Rate Limits
- Leverage existing 5-minute cache
- Hourly refresh during market hours (not per-command)
- Batch requests in get_all_positions_status

### Data Accuracy
- Fetch after hours at 4:15 PM for final prices
- Validate moneyness calculations with test cases
- Handle stale data gracefully (show timestamp)

### Database Growth
- position_snapshots table grows daily
- One row per open position per day
- Estimate: 10 positions * 365 days = 3,650 rows/year (minimal)
- Future: Add archive/cleanup for old closed positions

### Error Handling
- Continue processing other positions if one fails
- Log warnings for failed price fetches
- Gracefully handle missing data
- Return None instead of crashing on errors

## Testing Strategy

### Unit Tests
- All calculation logic (moneyness, risk, DTE)
- Database operations (CRUD for snapshots)
- Cache behavior and TTL
- Error handling paths

### Integration Tests
- End-to-end workflows
- CLI command outputs
- Multiple position scenarios
- Daily snapshot creation

### Manual Testing
- Test with live market data
- Verify timestamps and caching
- Confirm cron job integration
- Check visual formatting of risk indicators

## Acceptance Criteria

| Criterion | Verification |
|-----------|-------------|
| DTE displays correctly | Shows "X days (Y trading days)" format |
| ITM detection for puts | current_price <= strike → ITM |
| ITM detection for calls | current_price >= strike → ITM |
| Risk levels correct | HIGH=ITM, MEDIUM=OTM 0-5%, LOW=OTM >5% |
| Status shows live data | Current price, DTE, moneyness displayed |
| List shows monitoring | Table includes all monitoring columns |
| Refresh creates snapshots | One per position per day, no duplicates |
| Cache respected | No API call if data < 5 min old |
| Force refresh works | --refresh bypasses cache |
| HIGH risk highlighted | Visual warning for ITM positions |

## Future Enhancements (Out of Scope)

- Real-time streaming updates (websockets)
- Push notifications or email alerts
- Web dashboard for visualization
- Backtesting with historical snapshots
- Machine learning on position evolution patterns
- Risk score prediction based on historical trends

## Estimated Effort

**Phase 1 (Models & DB)**: Small - straightforward dataclasses and schema
**Phase 2 (Core Logic)**: Medium - calculation logic needs careful testing
**Phase 3 (Repository)**: Small - standard CRUD operations
**Phase 4 (Manager)**: Small - delegation to monitor
**Phase 5 (CLI)**: Medium - display formatting and user experience
**Phase 6 (Utilities)**: Small - likely already exist or simple to create
**Phase 7 (Exports)**: Small - bookkeeping
**Phase 8 (Testing)**: Medium - comprehensive test coverage required
**Phase 9 (Documentation)**: Small to Medium - good docs critical for users

**Total**: Implementation can proceed incrementally, testing as each phase completes.
