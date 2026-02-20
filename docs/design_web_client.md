# System Design Document: Wheel Strategy Web Client

## 1. Architecture Overview

### 1.1 High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         Browser                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                   Web Client (Vanilla JS)                   │  │
│  │                                                             │  │
│  │  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌──────────┐ │  │
│  │  │Dashboard │  │Positions │  │Recommend  │  │ Trades   │ │  │
│  │  │  View    │  │  View    │  │  View     │  │  View    │ │  │
│  │  └────┬─────┘  └────┬─────┘  └─────┬─────┘  └────┬─────┘ │  │
│  │       │              │              │              │        │  │
│  │  ┌────┴──────────────┴──────────────┴──────────────┴────┐  │  │
│  │  │                  API Service Layer                     │  │  │
│  │  │  api.js — fetch wrapper, error handling, base URL      │  │  │
│  │  └──────────────────────┬─────────────────────────────┘  │  │
│  │                         │                                  │  │
│  │  ┌──────────────────────┴─────────────────────────────┐  │  │
│  │  │              State / Store (app.js)                  │  │  │
│  │  │  - positions[], portfolio, refreshTimer, config      │  │  │
│  │  └────────────────────────────────────────────────────┘  │  │
│  │                                                             │  │
│  │  ┌───────────────┐  ┌────────────┐  ┌──────────────────┐ │  │
│  │  │ Slide-out     │  │ Toast      │  │ Status Bar       │ │  │
│  │  │ Panel         │  │ System     │  │ (persistent)     │ │  │
│  │  └───────────────┘  └────────────┘  └──────────────────┘ │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                              │
                         HTTP (fetch)
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                    FastAPI Server (existing)                       │
│                                                                    │
│  Static Files (/static/*)          API Endpoints (/api/v1/*)     │
│  ├── index.html                    ├── portfolios                 │
│  ├── dist/                         ├── wheels                     │
│  │   ├── app.js                    ├── trades                     │
│  │   └── style.css                 ├── recommendations            │
│  └── assets/                       ├── positions                  │
│                                    └── health                     │
└──────────────────────────────────────────────────────────────────┘
```

### 1.2 Component Responsibilities

| Component | Responsibility |
|-----------|---------------|
| `api.js` | HTTP client wrapping `fetch()`. Handles base URL, error responses, JSON parsing. Single point for all API calls. |
| `app.js` | Application state, initialization, auto-refresh timer, view routing. Coordinates between views. |
| `dashboard.js` | Renders portfolio summary cards and positions table. Entry point view. |
| `positions.js` | Position detail view, init/import forms, archive action. |
| `recommendations.js` | Fetches and displays top 3 candidates per symbol. One-click trade recording. |
| `trades.js` | Trade recording, expiration, close-early forms. Trade history table. |
| `performance.js` | Performance metrics display and CSV export. |
| `panel.js` | Slide-out panel component for forms. Open/close, pre-fill support. |
| `toast.js` | Toast notification system. Success/error/warning with auto-dismiss. |
| `statusbar.js` | Persistent status bar: connection state, last refresh, countdown timer. |

---

## 2. File Structure

```
src/
├── client/                          # Web client source (Vite project)
│   ├── index.html                   # Entry point HTML
│   ├── vite.config.js               # Vite configuration
│   ├── package.json                 # Minimal dependencies (vite, tailwindcss)
│   ├── tailwind.config.js           # Tailwind configuration
│   ├── src/
│   │   ├── main.js                  # Entry: imports, init, mount
│   │   ├── app.js                   # App state, routing, refresh loop
│   │   ├── api.js                   # API service layer
│   │   ├── views/
│   │   │   ├── dashboard.js         # Portfolio summary + positions table
│   │   │   ├── positions.js         # Position detail, init/import
│   │   │   ├── recommendations.js   # Recommendation candidates
│   │   │   ├── trades.js            # Trade management + history
│   │   │   └── performance.js       # Performance metrics
│   │   ├── components/
│   │   │   ├── panel.js             # Slide-out panel
│   │   │   ├── toast.js             # Toast notifications
│   │   │   ├── statusbar.js         # Status bar
│   │   │   ├── sidebar.js           # Navigation sidebar
│   │   │   └── table.js             # Sortable table helper
│   │   └── style.css                # Tailwind directives + custom styles
│   └── public/
│       └── favicon.ico
│
├── server/
│   ├── main.py                      # Add static file mounting (existing)
│   └── ...                          # Existing server code
```

### 2.1 Build Output

Vite builds to `src/client/dist/` which FastAPI serves as static files.

- Development: `npm run dev` runs Vite dev server with proxy to FastAPI
- Production: `npm run build` outputs to `dist/`, FastAPI serves directly

---

## 3. Layout Design

### 3.1 Page Structure

```
┌──────────────────────────────────────────────────────────────────┐
│  ┌──────┐  ┌──────────────────────────────────────────────────┐  │
│  │      │  │                                                  │  │
│  │  S   │  │              Main Content Area                   │  │
│  │  I   │  │                                                  │  │
│  │  D   │  │  ┌──────────────────────────────────────────┐   │  │
│  │  E   │  │  │  Portfolio Summary (cards)                │   │  │
│  │  B   │  │  └──────────────────────────────────────────┘   │  │
│  │  A   │  │                                                  │  │
│  │  R   │  │  ┌──────────────────────────────────────────┐   │  │
│  │      │  │  │  Positions Table                          │   │  │
│  │  ----│  │  │  Symbol | State | Profile | Capital | ... │   │  │
│  │  Nav │  │  │  AAPL   | CASH  | conserv | $15,000 | ... │   │  │
│  │  ----│  │  │  MSFT   | SHARES| moderate| $20,000 | ... │   │  │
│  │      │  │  └──────────────────────────────────────────┘   │  │
│  │      │  │                                                  │  │
│  └──────┘  └──────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ Status Bar: ● Connected | Last refresh: 14:32:05 | Next: 3m │ │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 Sidebar Navigation

The sidebar is a narrow, fixed-width panel on the left with icon + label navigation:

| Icon | Label | View |
|------|-------|------|
| ◻ | Dashboard | Portfolio summary + all positions |
| ◎ | Recommend | Recommendations for eligible positions |
| ⬆ | Trades | Trade history + recording |
| ▣ | Performance | Performance metrics per symbol |

Active item highlighted. Sidebar collapses to icons only on narrower screens (but desktop-first for v1).

### 3.3 Slide-Out Panel

Used for all forms (init wheel, import shares, record trade, expire, close). Slides in from the right edge, overlaying the main content with a semi-transparent backdrop.

```
┌──────────────────────────────────────┬──────────────────┐
│                                      │                  │
│         Main Content (dimmed)        │   Slide-Out      │
│                                      │   Panel          │
│                                      │                  │
│                                      │   [Form Fields]  │
│                                      │                  │
│                                      │   [Submit]       │
│                                      │   [Cancel]       │
│                                      │                  │
└──────────────────────────────────────┴──────────────────┘
```

Width: ~400px fixed. Supports pre-filling fields when opened from a recommendation.

---

## 4. View Specifications

### 4.1 Dashboard View

**Portfolio Summary Cards** (top row, 4 cards):

| Card | Data Source |
|------|------------|
| Total Capital | Sum of `capital_allocated` across active wheels |
| Total Premium | Sum of premium from all closed trades |
| Open Positions | Count of wheels in `*_OPEN` states |
| Active Wheels | Count of active wheels |

**Positions Table** (below cards):

| Column | Source | Notes |
|--------|--------|-------|
| Symbol | `wheel.symbol` | Clickable — opens position detail |
| State | `wheel.state` | Color-coded badge (CASH=blue, SHARES=green, *_OPEN=yellow) |
| Profile | `wheel.profile` | |
| Capital | `wheel.capital_allocated` | Formatted as currency |
| Open Trade | `trade.direction + strike + expiration` | Only if open trade exists |
| Current Price | `position.current_price` | From monitoring endpoint |
| DTE | `position.dte_calendar` | Days to expiration, only for open trades |
| Risk | `position.risk_level` | Color-coded: LOW=green, MEDIUM=yellow, HIGH=red |
| Actions | Buttons | [Recommend] [Record] [Expire/Close] — context-dependent |

**Action buttons** vary by state:
- CASH: [Recommend] [Record Put]
- SHARES: [Recommend] [Record Call]
- CASH_PUT_OPEN: [Expire] [Close Early]
- SHARES_CALL_OPEN: [Expire] [Close Early]

### 4.2 Recommendations View

Shows all eligible positions (no open trade) with their top 3 candidates.

**Per-symbol recommendation block:**

```
┌─────────────────────────────────────────────────────────────────┐
│  AAPL — CASH — Conservative                    [Refresh]        │
├─────────────────────────────────────────────────────────────────┤
│  #  Strike   Exp       DTE  Premium  Contracts  P(ITM)  Yield  │
│  1  $220.00  02/28/26   14  $1.85     1         8.2%    24.1%  │  [Record]
│  2  $215.00  02/28/26   14  $1.20     1         5.1%    15.6%  │  [Record]
│  3  $222.50  03/07/26   21  $2.10     1        10.3%    18.3%  │  [Record]
├─────────────────────────────────────────────────────────────────┤
│  ⚠ Warnings: Earnings on 03/01/26                               │
└─────────────────────────────────────────────────────────────────┘
```

Each row's [Record] button opens the slide-out panel pre-filled with that candidate's data.

### 4.3 Trades View

**Trade History Table** (per symbol, selectable via dropdown or from position click):

| Column | Data |
|--------|------|
| Date | Trade opened date |
| Direction | PUT / CALL |
| Strike | Strike price |
| Expiration | Expiration date |
| Premium | Total premium collected |
| Outcome | [WIN] [ASSIGNED] [CALLED] [CLOSED] [OPEN] — color-coded |
| Net | Net premium after close (if applicable) |

**Inline actions** for open trades: [Expire] [Close Early] buttons in the row.

### 4.4 Performance View

**Per-symbol performance card:**

| Metric | Display |
|--------|---------|
| Total Premium | Currency |
| Total Trades | Count |
| Win Rate | Percentage |
| Puts Sold / Calls Sold | Count each |
| Assignments / Called Away | Count each |
| Avg Days Held | Number |
| Annualized Yield | Percentage |

**Export**: [Export CSV] button per symbol.

---

## 5. API Service Layer

### 5.1 `api.js` Design

Single module exporting all API functions. Uses `fetch()` with consistent error handling.

```
Configuration:
  BASE_URL = "" (same origin, relative paths)
  TIMEOUT = 30000ms

Functions (grouped by resource):

  // Health
  checkHealth() → { status, scheduler_status }

  // Portfolios
  listPortfolios() → Portfolio[]
  getPortfolio(id) → Portfolio
  getPortfolioSummary(id) → PortfolioSummary

  // Wheels
  createWheel(portfolioId, data) → Wheel
  listWheels(portfolioId, activeOnly) → Wheel[]
  getWheel(id) → Wheel
  updateWheel(id, data) → Wheel
  deleteWheel(id) → void

  // Trades
  recordTrade(wheelId, data) → Trade
  listTrades(wheelId) → Trade[]
  expireTrade(tradeId, priceAtExpiry) → Trade
  closeTrade(tradeId, closePrice) → Trade

  // Recommendations
  getRecommendation(wheelId, maxDte) → Recommendation
  getBatchRecommendations(symbols, maxDte) → BatchResponse

  // Positions
  getPositionStatus(wheelId) → PositionStatus
  getPortfolioPositions(portfolioId) → BatchPositionResponse
  getOpenPositions() → BatchPositionResponse

Error handling:
  - 4xx → throw with error message from response body
  - 5xx → throw with generic server error message
  - Network error → throw APIConnectionError
  - All errors include HTTP status code for caller inspection
```

### 5.2 Error Handling Pattern

```
try {
    const data = await api.recordTrade(wheelId, tradeData);
    toast.success("Trade recorded successfully");
    refreshPositions();
} catch (err) {
    toast.error(err.message);
}
```

---

## 6. State Management

### 6.1 Application State

No framework state management. A single `app.js` module holds state as plain objects and arrays, with functions to update state and trigger re-renders of affected views.

```
State shape:
{
    portfolioId: string | null,     // Active portfolio
    portfolio: Portfolio | null,    // Cached portfolio data
    wheels: Wheel[],                // All wheels in active portfolio
    positions: PositionStatus[],    // Monitoring data for open positions
    config: {
        refreshInterval: 300000,    // 5 minutes in ms
        maxDte: 14,                 // Default max DTE for recommendations
    },
    ui: {
        activeView: "dashboard",    // Current sidebar selection
        panelOpen: false,           // Slide-out panel state
        panelContent: null,         // What form to show in panel
        lastRefresh: Date | null,   // Last successful refresh timestamp
        connected: boolean,         // API health status
    }
}
```

### 6.2 Refresh Loop

```
On app init:
  1. checkHealth() → set connected status
  2. listPortfolios() → pick first (or configured default)
  3. listWheels(portfolioId) → populate wheels
  4. getPortfolioPositions(portfolioId) → populate positions
  5. Start interval timer

Every refreshInterval:
  1. checkHealth()
  2. getPortfolioPositions(portfolioId, force_refresh=true)
  3. Update positions in state
  4. Re-render affected views
  5. Update status bar timestamp and countdown
```

### 6.3 View Rendering

Each view module exports a `render(container, state)` function. When state changes, the app calls the active view's render function with the updated state. Views construct DOM via template literals and `innerHTML`, or via `document.createElement` for interactive elements with event listeners.

---

## 7. Visual Design

### 7.1 Theme

Data-dense, terminal-inspired dark theme.

| Element | Color |
|---------|-------|
| Background | `#0f1117` (near-black) |
| Surface/Cards | `#1a1d27` (dark gray) |
| Borders | `#2a2d3a` (subtle gray) |
| Primary text | `#e2e8f0` (light gray) |
| Secondary text | `#94a3b8` (muted gray) |
| Accent (links, active) | `#60a5fa` (blue) |
| Success / LOW risk | `#22c55e` (green) |
| Warning / MEDIUM risk | `#eab308` (yellow) |
| Error / HIGH risk | `#ef4444` (red) |
| Monospace font | `JetBrains Mono`, `Fira Code`, or `monospace` fallback |
| Body font | System font stack (or `Inter` if loading a web font) |

### 7.2 Density

- Compact row height in tables (32-36px)
- Minimal padding on cards (12-16px)
- Small font sizes (13-14px body, 12px table data)
- No unnecessary whitespace between sections
- Borders preferred over shadows for visual separation

### 7.3 Typography

- Numbers: monospace, right-aligned in tables
- Currency: always 2 decimal places with $ prefix
- Percentages: 1 decimal place with % suffix
- Dates: YYYY-MM-DD format (matching API/CLI convention)

---

## 8. FastAPI Integration

### 8.1 Static File Serving

Add to `src/server/main.py`:

```
Mount the built client files at /static/ path.
Serve index.html for the root route (/).
```

The production build output (`src/client/dist/`) is mounted as a static directory. The root URL (`/`) serves `index.html`. All `/api/v1/` routes continue to work as before.

### 8.2 Development Workflow

During development:
- Vite dev server runs on port 5173 with hot reload
- Vite proxies `/api/v1/*` and `/health` to FastAPI on port 8000
- Developer accesses `http://localhost:5173`

For production:
- `npm run build` outputs to `dist/`
- FastAPI serves everything from one port (8000)

### 8.3 Vite Configuration

```
vite.config.js:
  - proxy: /api/* → http://localhost:8000
  - proxy: /health → http://localhost:8000
  - build.outDir: dist/
```

---

## 9. Component Interaction Flows

### 9.1 Init Wheel Flow

```
User clicks [+ New Wheel] button on Dashboard
  → panel.open("init-wheel")
  → User fills: symbol, capital, profile
  → User clicks [Create]
  → api.createWheel(portfolioId, data)
  → On success: toast.success(), panel.close(), refreshPositions()
  → On error: toast.error(message), form stays open
```

### 9.2 Recommendation → Trade Flow

```
User navigates to Recommendations view
  → For each eligible wheel: api.getRecommendation(wheelId, maxDte)
  → Display top 3 candidates per symbol
  → User clicks [Record] on a candidate
  → panel.open("record-trade", prefilled={symbol, direction, strike, expiration, premium, contracts})
  → User reviews pre-filled data, adjusts if needed
  → User clicks [Record Trade]
  → api.recordTrade(wheelId, tradeData)
  → On success: toast.success(), panel.close(), refreshPositions()
```

### 9.3 Expire Trade Flow

```
User clicks [Expire] on an open position
  → panel.open("expire-trade", {wheelId, tradeId, symbol, strike, direction})
  → User enters: stock price at expiration
  → User clicks [Submit]
  → api.expireTrade(tradeId, priceAtExpiry)
  → Response includes outcome (expired_worthless, assigned, called_away)
  → toast.success("AAPL put expired worthless — $150 premium collected")
  → panel.close(), refreshPositions()
```

### 9.4 Auto-Refresh Flow

```
Every 5 minutes (configurable):
  → api.checkHealth() → update connected status
  → api.getPortfolioPositions(portfolioId, force_refresh=true)
  → Update state.positions
  → Re-render active view if it depends on position data
  → Update status bar: "Last refresh: HH:MM:SS"
  → Reset countdown timer
```

---

## 10. Constraints and Dependencies

| Constraint | Detail |
|------------|--------|
| FastAPI server must be running | The web client is non-functional without the backend |
| Schwab OAuth tokens must be valid | Price/options data requires authenticated Schwab API access |
| Single portfolio at a time | UI shows one portfolio; user selects via dropdown if multiple exist |
| No offline capability | All data comes from API; no local storage caching in v1 |
| No WebSocket support | Polling only; server-sent events or WebSockets are deferred |

---

## 11. Future Considerations (not in scope for v1)

These are noted for architectural awareness but are explicitly out of scope:

- **WebSocket for real-time updates**: Replace polling with push-based updates
- **Dark/light theme toggle**: Currently dark-only
- **Volatility charts**: Sparklines or charts showing RV/IV over time
- **Position P&L visualization**: Chart showing premium collected over lifecycle
- **Keyboard navigation**: Shortcuts for power users (k/j navigation, enter to select)
- **Mobile responsive layout**: Adapt for tablet/phone viewports
- **Multi-portfolio dashboard**: Side-by-side comparison or aggregate view

---

## 12. Implementation Notes

This section documents deviations between the original design and the actual implementation.

### 12.1 Tailwind CSS v4

Tailwind CSS v4 was used instead of v3. Key differences:
- Uses `@import "tailwindcss"` instead of `@tailwind base/components/utilities` directives
- Configured via `@tailwindcss/vite` plugin — no separate `tailwind.config.js` file needed
- Dark theme colors defined as CSS custom properties in `style.css`

### 12.2 Static File Mount Path

FastAPI mounts built assets at `/assets/` (not `/static/`) to match Vite's default build output structure (`dist/assets/`). A catch-all route serves `index.html` for unmatched paths. When no `dist/` directory exists, the original JSON root endpoint is preserved.

### 12.3 File Organization

- **Forms directory**: Form renderers are in `src/client/src/forms/` (init-wheel.js, record-trade.js, expire-trade.js, close-trade.js) rather than embedded in view files. Each form registers itself with the panel system via `panel.registerForm()`.
- **Format utility**: A shared `src/client/src/format.js` module provides `formatCurrency()`, `formatPercent()`, `formatDate()`, and `formatNumber()` used across all views.
- **No `positions.js` view**: Position management (init wheel, import shares, archive) is handled directly in the dashboard view and panel forms, rather than a separate positions view.

### 12.4 Import Shares

The "import shares" functionality is merged into the init-wheel form via a "Shares — Sell Calls" radio option that toggles between capital fields and shares/cost-basis fields, rather than being a separate form.

### 12.5 Portfolio Selector

The portfolio selector dropdown is rendered in the sidebar (below the logo) via `sidebar.renderPortfolioSelector()`. It only appears when multiple portfolios exist. Changing the selection triggers a full data reload (wheels + positions).

### 12.6 API Field Names

- `expireTrade()` sends `{ price_at_expiry }` (not `stock_price_at_expiry`)
- Position monitoring uses `dte_calendar` (not `dte`) and `risk_level` from the `PositionStatusResponse` model
- `BatchPositionResponse` wraps positions in a `{ positions: [...] }` object

### 12.7 State Shape

The implemented state includes `portfolios` (array of all portfolios) and `loading` (boolean) in the `ui` object, which were not in the original design but are needed for the portfolio selector and loading states respectively.
