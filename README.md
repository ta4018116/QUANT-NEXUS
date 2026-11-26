# QUANT NEXUS

Responsive quantitative market intelligence and paper-trading web application.

## Safety
- Simulation / paper-trading only.
- Live order execution is disabled by design; no live-order endpoint exists.
- Exchange API credentials are not used. Public market data is read from Bybit with OKX fallback.
- Crypto Spot and USDT linear futures are connected. Forex, US stocks, indices and commodities are explicitly marked as unconnected until real providers are configured.

## Implemented modules
- Multi-timeframe analysis (5m, 15m, 1h, 4h).
- EMA20/EMA50, RSI14, MACD(12,26,9), VWAP and candle-volume ratio.
- Market scanner with 32/64/128/256/AUTO depth and bounded concurrency.
- Analysis command API for trend, levels, volume/liquidity proxy, breakouts, candle patterns, momentum divergence, multi-timeframe and Spot/Futures comparison.
- EMA20/EMA50 historical backtest with fee assumptions, win rate, profit factor, expectancy and drawdown.
- Paper portfolio with directional LONG/SHORT PnL and state persistence adapter.

## Data storage and Render deployment
The portfolio stores its state in SQLite by default:
- Local: `QUANT_NEXUS_DB_PATH` (default `data/quant_nexus.sqlite3`).
- PostgreSQL: set `DATABASE_URL` to a PostgreSQL connection string. The app creates its `quant_paper_state` table automatically.

**Important for Render:** Free Render web services use an ephemeral filesystem. SQLite data on a free web service is lost when the service restarts, spins down, or redeploys. For durable hosted paper-trade history, connect a persistent PostgreSQL database through `DATABASE_URL`. Render's free Postgres offering is time-limited; use a database plan with retention appropriate for the data you need. The UI reports which storage mode is active.

## API endpoints
- `GET /health`
- `GET /api/overview`
- `GET /api/engine/status`
- `GET /api/markets?category=spot|linear`
- `GET /api/scan?category=spot|linear&interval=15m&depth=AUTO`
- `GET /api/klines/{symbol}`
- `GET /api/multi-timeframe/{symbol}`
- `POST /api/commands/execute`
- `GET /api/backtest/{symbol}`
- `GET /api/paper`
- `POST /api/paper`
- `POST /api/paper/{trade_id}/close?exit_price=...`

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000. The web dashboard is served from `app/static/index.html`.

## Validation
GitHub Actions compiles the application and runs the API regression suite on pull requests and main-branch updates. Public market-data tests should use mocked provider responses so CI does not depend on exchange availability.
