# Wheel Strategy Position Monitoring Guide

## Overview

The Wheel Strategy Tool now includes comprehensive position monitoring capabilities that provide real-time visibility into your open positions. Monitor days to expiration (DTE), moneyness, and risk levels to make informed decisions about your trades.

## Features

### Real-Time Position Status
- **Current Price**: Live market price for your underlying
- **Days to Expiration**: Both calendar and trading days
- **Moneyness**: How far in/out of the money your position is
- **Risk Assessment**: LOW/MEDIUM/HIGH risk levels with visual indicators
- **Assignment Risk**: Immediate alerts for positions at risk

### Historical Tracking
- Daily snapshots of position evolution
- Track price movement relative to strikes over time
- Analyze how positions moved through their lifecycle

## Using the Monitoring Features

### View Status for a Single Position

```bash
wheel status AAPL
```

**With live monitoring data (when position is open):**
```
======================================================================
  AAPL - CASH_PUT_OPEN
======================================================================

Position:
  Profile: conservative
  Capital: $20,000.00

Open PUT:
  Strike: $150.00
  Expiration: 2025-02-21
  Premium: $250.00 ($2.50/share)
  Contracts: 1

Live Status (as of 2025-01-28 14:30:00):
  Current Price: $155.00
  DTE: 24 days (17 trading days)
  Moneyness: OTM by 3.3%
  Risk Level: 🟡 MEDIUM
```

### Force Fresh Data from API

```bash
wheel status AAPL --refresh
```

The `--refresh` flag bypasses the 5-minute cache and fetches fresh market data.

### View All Positions

```bash
wheel status --all
```

Shows detailed status for all wheels with open positions.

### List Portfolio Overview

```bash
wheel list
```

**Output:**
```
Symbol   State                 Strike  Current          DTE    Moneyness     Risk
=====================================================================================
AAPL     cash_put_open        $150.00 $155.00   24d (17t)   OTM by 3.3%  🟡 MED
MSFT     shares                   ---     ---          ---           ---    ---
NVDA     shares_call_open     $800.00 $820.00   30d (21t)   ITM by 2.5%  🔴 HIG

Total wheels: 3
Open positions: 2

⚠️  1 position(s) at HIGH RISK (ITM)
```

### Refresh for Latest Data

```bash
wheel list --refresh
```

## Risk Levels Explained

### 🟢 LOW RISK
- **Condition**: Out of the money by more than 5%
- **Meaning**: Comfortable safety margin, low probability of assignment
- **Action**: Continue monitoring, position on track

### 🟡 MEDIUM RISK
- **Condition**: Out of the money by 0-5%
- **Meaning**: Approaching strike price, entering danger zone
- **Action**: Watch closely, consider adjusting if needed

### 🔴 HIGH RISK
- **Condition**: In the money (any amount)
- **Meaning**: Assignment/exercise is likely at expiration
- **Action**: Decide whether to:
  - Close position early (buy back the option)
  - Accept assignment and transition states
  - Adjust strike or roll to new expiration

## Moneyness Calculation

### For Puts (Selling Cash-Secured Puts)
- **ITM (In The Money)**: Current price ≤ Strike
  - Risk: You will likely be assigned and buy shares at the strike price
- **OTM (Out The Money)**: Current price > Strike
  - Goal: Option expires worthless, you keep the premium

### For Calls (Selling Covered Calls)
- **ITM (In The Money)**: Current price ≥ Strike
  - Risk: Your shares will likely be called away at the strike price
- **OTM (Out The Money)**: Current price < Strike
  - Goal: Option expires worthless, you keep shares and premium

## Historical Snapshots

### Creating Daily Snapshots

```bash
wheel refresh
```

This command:
- Fetches fresh quotes for all open positions
- Creates daily snapshots in the database
- Should be run once per day (typically after market close)

**Output:**
```
Refreshing all open positions...
Created 3 position snapshot(s) for today
```

If run multiple times on the same day:
```
Refreshing all open positions...
No new snapshots created (already up-to-date for today)
```

### Scheduling Automatic Snapshots

Add to your crontab for automatic daily tracking:

```bash
# Daily at 4:15 PM ET (after market close) on weekdays
15 16 * * 1-5 cd /path/to/options_income && wheel refresh
```

Adjust timezone as needed for your location.

## Understanding DTE (Days to Expiration)

The tool displays DTE in two formats:

### Calendar Days
- Total days remaining until expiration date
- Includes weekends and holidays
- Example: "24 days"

### Trading Days
- Business days (Mon-Fri) remaining
- Excludes weekends (simplified - no holiday calendar)
- Example: "17 trading days"

**Display Format**: "24 days (17 trading days)"

## Best Practices

### Daily Routine
1. **Morning Check**: `wheel list` to see portfolio at a glance
2. **Monitor HIGH RISK**: Check any ITM positions
3. **After Close**: `wheel refresh` to capture today's snapshot

### When to Take Action

**🔴 HIGH RISK (ITM) Positions:**
- Review immediately when they appear
- Calculate cost of closing early vs. accepting assignment
- Consider rolling to new expiration if still bullish/bearish

**🟡 MEDIUM RISK (Near Strike) Positions:**
- Increase monitoring frequency
- Prepare contingency plans
- Watch for earnings or events that could move price

**🟢 LOW RISK (Comfortable OTM) Positions:**
- Monitor periodically
- On track to collect full premium
- Focus attention on higher-risk positions

### Position Management Tips

1. **Set Personal Thresholds**: Decide in advance when you'll close positions (e.g., "if ITM with >14 DTE")

2. **Track Your Patterns**: Use historical snapshots to see how your positions typically evolve

3. **Earnings Awareness**: HIGH RISK becomes even higher if earnings announcement is coming

4. **Time Decay Works For You**: The closer to expiration while OTM, the better for premium collection

## Data Freshness

### Caching Behavior
- Price data is cached for 5 minutes to minimize API calls
- `--refresh` flag bypasses cache for immediate fresh data
- Hourly automatic refresh during market hours (when tool is running)
- After-hours refresh at 4:15 PM ET

### When Data is Stale
If you see old timestamps, the issue might be:
- No price data provider configured
- API quota exceeded
- Market closed (last available data shown)
- Network connectivity issues

## Programmatic Access

You can also access monitoring features via the Python API:

```python
from wheel_strategy_tool import WheelManager

manager = WheelManager()

# Get status for single position
status = manager.get_position_status("AAPL", force_refresh=True)
if status:
    print(f"Risk: {status.risk_level}")
    print(f"Moneyness: {status.moneyness_label}")

# Get all positions
all_statuses = manager.get_all_positions_status(force_refresh=True)
for position, trade, status in all_statuses:
    print(f"{position.symbol}: {status.risk_level}")

# Create daily snapshots
count = manager.refresh_snapshots()
print(f"Created {count} snapshots")
```

## Troubleshooting

### "No price data provider configured"
- Ensure Schwab OAuth is set up correctly
- Check API credentials in configuration
- Verify network connectivity

### Empty monitoring data in list command
- No open positions currently (all positions in CASH or SHARES state)
- Price provider unavailable
- Run with `--refresh` to force fetch

### Snapshots not creating
- No open positions to snapshot
- Already created snapshot for today (not an error)
- Use `wheel refresh` command explicitly

## Related Commands

- `wheel init` - Create new wheel position
- `wheel recommend` - Get next trade recommendation
- `wheel record` - Record sold option
- `wheel expire` - Record expiration outcome
- `wheel performance` - View performance metrics

## See Also

- [Wheel Strategy Tool PRD](prd_wheel_strategy_tool.md)
- [System Design](design_wheel_strategy_tool.md)
- [Implementation Plan](implementation_plan_wheel_monitoring.md)
