# Quick Start Guide - Options Income

## Prerequisites

- Python 3.11+
- Node.js 20+ and npm
- Schwab API credentials (app key + secret) for live market data

## 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

## 2. Initialize the Database

On first run, create the database and default portfolio:

```bash
python scripts/init_database.py --force --sample-data
```

This creates the SQLite database at `~/.wheel_strategy/trades.db` with the required schema and a default portfolio.

To reset the database and start fresh, run the same command again — the `--force` flag will overwrite the existing database.

## 3. Start the API Server

```bash
uvicorn src.server.main:app --reload
```

The server runs at `http://localhost:8000`. API docs are at `http://localhost:8000/docs`.

## 4. Web Client Development

### Development Mode (with hot reload)

```bash
cd src/client
npm install
npm run dev
```

Open `http://localhost:5173`. The Vite dev server proxies API requests to FastAPI on port 8000.

### Production Build

```bash
cd src/client
npm run build
```

The build outputs to `src/client/dist/`. Once built, FastAPI serves the web client at `http://localhost:8000/` alongside the API.

## 5. CLI Usage

The wheel strategy tool is also available via CLI:

```bash
# List portfolios
python -m src.wheel.cli portfolio list

# Get recommendations
python -m src.wheel.cli recommend AAPL

# Record a trade
python -m src.wheel.cli trade record AAPL put 145.00 2026-03-14 1.50
```

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| Auto-refresh interval | 5 minutes | Web client polling interval for position data |
| Max DTE | 14 days | Default maximum days to expiration for recommendations |
| API port | 8000 | FastAPI server port |
| Dev server port | 5173 | Vite development server port |

## Running Tests

```bash
# Server tests
pytest tests/server/ -v

# Wheel strategy tests
pytest tests/wheel/ -v

# All tests
pytest
```

## Project Structure

```
src/
  client/          Web client (Vite + vanilla JS + Tailwind CSS)
  server/          FastAPI backend server
  wheel/           Wheel strategy engine and CLI
tests/
  server/          Server API tests
  wheel/           Wheel strategy tests
docs/              Design documents and guides
```
