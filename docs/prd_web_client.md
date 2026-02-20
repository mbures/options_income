# Product Requirements Document: Wheel Strategy Web Client

## 1. Overview

### 1.1 Purpose

The Wheel Strategy Web Client is a browser-based interface for managing wheel strategy positions. It provides a visual, data-dense dashboard for monitoring positions, recording trades, viewing recommendations, and tracking performance — replacing the CLI as the primary user interface while reusing the existing FastAPI backend.

### 1.2 Background

The system currently has three layers: a CLI tool, a FastAPI backend server, and core business logic. The CLI communicates with the backend via HTTP API calls, with fallback to direct database access. The web client will become a third consumer of the same API, served directly by the FastAPI process alongside the API endpoints.

### 1.3 Goals

- Provide a visual interface for the complete wheel strategy lifecycle (init, recommend, record, monitor, expire)
- Surface monitoring data (DTE, moneyness, risk level) without requiring terminal access
- Allow one-click trade recording from recommendations to reduce friction
- Show top 3 recommendation candidates per symbol for informed decision-making
- Auto-refresh position data on a configurable interval (default 5 minutes)
- Match the feature set of the CLI tool for core workflow operations

### 1.4 Non-Goals

- Automated order execution (the tool provides recommendations; the user executes trades manually on their broker platform)
- Advanced analytics (volatility regime analysis, ladder builder, weekly overlay scanner) — deferred to future versions
- Mobile-specific responsive layout — desktop-first for v1
- User authentication or multi-user support — single-user local tool
- Real-time streaming data (WebSockets) — polling-based refresh is sufficient for v1

---

## 2. User Stories

### 2.1 Dashboard & Monitoring

**US-W1: View Portfolio Summary**
> As a trader, I want to see aggregate portfolio metrics (total capital deployed, total premium collected, number of open positions, active wheels) when I open the app so that I get an immediate overview of my portfolio health.

**US-W2: View All Positions**
> As a trader, I want to see a table of all my wheel positions with their current state, profile, capital, and open trade details so that I can quickly scan my portfolio.

**US-W3: Monitor Open Positions**
> As a trader, I want to see live monitoring data (current price, DTE, moneyness, risk level) for positions with open trades so that I can assess assignment risk at a glance.

**US-W4: Auto-Refresh Data**
> As a trader, I want position data to auto-refresh every 5 minutes (configurable) so that I see current market conditions without manual action.

**US-W5: Identify High-Risk Positions**
> As a trader, I want positions that are ITM or near-the-money to be visually highlighted (color-coded risk levels) so that I can immediately identify positions requiring attention.

### 2.2 Position Management

**US-W6: Initialize a New Wheel**
> As a trader, I want to create a new wheel position by specifying a symbol, capital amount, and risk profile through a slide-out form so that I can begin tracking a new position.

**US-W7: Import Existing Shares**
> As a trader, I want to import shares I already own (symbol, share count, cost basis) so that I can start writing covered calls against them.

**US-W8: Archive a Wheel**
> As a trader, I want to deactivate a wheel position that I no longer want to track so that my active positions list stays clean.

### 2.3 Recommendations

**US-W9: View Recommendations**
> As a trader, I want to see the top 3 recommended options to sell for a position, ranked by bias score, showing strike, premium, DTE, P(ITM), sigma distance, and annualized yield so that I can make an informed trade decision.

**US-W10: One-Click Trade Recording**
> As a trader, I want to click "Record Trade" on a recommendation and have the trade form pre-filled with that recommendation's details so that I can record the trade with minimal data entry.

**US-W11: Request Recommendations for All Positions**
> As a trader, I want to get recommendations for all eligible wheels (those without open positions) in one action so that I can evaluate opportunities across my portfolio.

### 2.4 Trade Management

**US-W12: Record a Trade**
> As a trader, I want to record a sold option (symbol, direction, strike, expiration, premium, contracts) through a slide-out form so that the system tracks my open position.

**US-W13: Record Expiration**
> As a trader, I want to record the stock price at expiration so that the system determines the outcome (expired worthless, assigned, or called away) and transitions the wheel state.

**US-W14: Close Trade Early**
> As a trader, I want to close a trade early by entering the buy-back price so that the system calculates my net premium and updates the position.

### 2.5 Performance & History

**US-W15: View Performance Metrics**
> As a trader, I want to see performance metrics per symbol (total premium, win rate, puts sold, calls sold, assignments, called away events) so that I can evaluate each wheel's effectiveness.

**US-W16: View Trade History**
> As a trader, I want to see a complete trade history table for a wheel showing date, direction, strike, expiration, premium, outcome, and net result so that I can review past activity.

---

## 3. Functional Requirements

### 3.1 Dashboard

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-D1 | Display portfolio summary: total capital, total premium collected, open positions count, active wheels count | Must |
| FR-D2 | Display positions table: symbol, state, profile, capital allocated, open trade details | Must |
| FR-D3 | For positions with open trades, show: current price, DTE (calendar + trading), moneyness label, risk level with color coding | Must |
| FR-D4 | Auto-refresh position data on a configurable interval (default: 5 minutes) | Must |
| FR-D5 | Manual refresh button to force immediate data update | Must |
| FR-D6 | Risk level color coding: LOW=green, MEDIUM=yellow, HIGH=red | Must |
| FR-D7 | Sort positions table by any column | Should |
| FR-D8 | Display last refresh timestamp in status bar | Must |

### 3.2 Position Management

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-P1 | Init wheel form: symbol (required), capital (required for CASH start), shares + cost basis (required for SHARES start), profile selector | Must |
| FR-P2 | Import shares form: symbol, shares, cost basis (all required) | Must |
| FR-P3 | Archive wheel action with confirmation | Must |
| FR-P4 | Validate inputs (positive numbers, non-empty symbol, valid profile) | Must |
| FR-P5 | Show success/error feedback after each operation | Must |

### 3.3 Recommendations

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-R1 | Show top 3 candidates per symbol, ranked by bias score | Must |
| FR-R2 | Each candidate shows: strike, expiration, DTE, premium/share, total premium, contracts, P(ITM), sigma distance, annualized yield, bias score | Must |
| FR-R3 | Display warnings on recommendations (high P(ITM), low yield, short DTE, earnings conflict) | Must |
| FR-R4 | "Record Trade" button on each candidate that opens pre-filled trade form | Must |
| FR-R5 | Batch recommendations for all eligible positions | Should |
| FR-R6 | Respect max_dte configuration when requesting recommendations | Must |

### 3.4 Trade Management

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-T1 | Record trade form: symbol, direction (put/call), strike, expiration date, premium per share, contracts | Must |
| FR-T2 | Expire trade form: stock price at expiration | Must |
| FR-T3 | Close trade form: buy-back price per share | Must |
| FR-T4 | Show calculated outcome after expiration (expired worthless, assigned, called away) | Must |
| FR-T5 | Validate trade inputs against wheel state (e.g., cannot record put if already has open put) | Must |

### 3.5 Performance & History

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-PH1 | Per-symbol performance view: total premium, total trades, win rate, puts sold, calls sold, assignments, called away | Must |
| FR-PH2 | Trade history table: date, direction, strike, expiration, premium, outcome, net result | Must |
| FR-PH3 | Outcome icons/labels matching CLI: [WIN], [ASSIGNED], [CALLED], [CLOSED] | Must |
| FR-PH4 | Export trade history to CSV | Should |

### 3.6 Notifications & Status

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-N1 | Toast notifications for transient events (trade recorded, trade expired, errors) | Must |
| FR-N2 | Persistent status bar showing: API connection status, last refresh timestamp, auto-refresh countdown | Must |
| FR-N3 | Toast auto-dismiss after 5 seconds; errors persist until dismissed | Must |

---

## 4. Non-Functional Requirements

### 4.1 Technology

| ID | Requirement |
|----|-------------|
| NFR-T1 | Vanilla JavaScript — no framework (React, Vue, etc.) |
| NFR-T2 | Tailwind CSS for styling (via CDN or Vite build) |
| NFR-T3 | Vite for development server (hot reload) and production build |
| NFR-T4 | Served as static files by the existing FastAPI server |
| NFR-T5 | All data access via the existing `/api/v1/` REST endpoints |
| NFR-T6 | No additional backend dependencies — client is purely frontend |

### 4.2 Performance

| ID | Requirement |
|----|-------------|
| NFR-P1 | Initial page load under 2 seconds on localhost |
| NFR-P2 | API calls should complete within the existing 30-second timeout |
| NFR-P3 | Auto-refresh should not block UI interaction |

### 4.3 Compatibility

| ID | Requirement |
|----|-------------|
| NFR-C1 | Support modern evergreen browsers (Chrome, Firefox, Edge) |
| NFR-C2 | Desktop viewport (1280px+) — no mobile layout required for v1 |

---

## 5. API Dependencies

The web client consumes the following existing API endpoints. No new backend endpoints are required.

### Portfolios
- `GET /api/v1/portfolios/` — List portfolios
- `GET /api/v1/portfolios/{id}` — Get portfolio details
- `GET /api/v1/portfolios/{id}/summary` — Portfolio summary metrics

### Wheels
- `POST /api/v1/portfolios/{id}/wheels` — Create wheel
- `GET /api/v1/portfolios/{id}/wheels` — List wheels in portfolio
- `GET /api/v1/wheels/{id}` — Get wheel details
- `GET /api/v1/wheels/{id}/state` — Get wheel state
- `PUT /api/v1/wheels/{id}` — Update wheel
- `DELETE /api/v1/wheels/{id}` — Delete/archive wheel

### Trades
- `POST /api/v1/wheels/{id}/trades` — Record trade
- `GET /api/v1/wheels/{id}/trades` — List trades for wheel
- `GET /api/v1/trades/{id}` — Get trade details
- `POST /api/v1/trades/{id}/expire` — Expire trade
- `POST /api/v1/trades/{id}/close` — Close trade early

### Recommendations
- `GET /api/v1/wheels/{id}/recommend` — Get recommendation (supports `max_dte` query param)
- `POST /api/v1/wheels/recommend/batch` — Batch recommendations

### Position Monitoring
- `GET /api/v1/wheels/{id}/position` — Position status (DTE, moneyness, risk)
- `GET /api/v1/portfolios/{id}/positions` — All positions in portfolio
- `GET /api/v1/positions/open` — All open positions

### System
- `GET /health` — Health check (used for connection status indicator)

---

## 6. Out of Scope for v1

The following features are explicitly deferred:

- Volatility calculation display (realized, implied, blended)
- Volatility regime analysis
- Strike optimization visualizations
- Ladder builder UI
- Weekly overlay scanner
- Portfolio creation/deletion from the web UI (use CLI for portfolio setup)
- Multi-portfolio view (single portfolio at a time, selectable via dropdown if multiple exist)
- Dark/light theme toggle (dark theme only for v1)
- Keyboard shortcuts
- Data export to JSON format (CSV only)
