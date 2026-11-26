# QUANT NEXUS X

A responsive, Arabic-first quantitative market intelligence and simulation platform.

## Live market coverage
- Crypto Spot and USDT linear Futures data through Bybit, with OKX fallback where supported.
- Forex, US equities, indices and commodities are shown as not connected until a dedicated provider is configured. The application does not fabricate prices for unavailable markets.

## Analysis and research
- EMA 20/50, RSI 14, MACD 12/26/9, VWAP, volume ratio and ATR 14.
- Explainable signal labels and a short list of contributing observations.
- Multi-timeframe snapshots across 5m, 15m, 1h and 4h.
- Order-book spread/depth imbalance and recent large-trade outlier summaries.
- EMA crossover historical simulation with next-bar-open fills, fees and slippage, and mark-to-market drawdown.
- Position sizing helper with a maximum configured risk input of 2% of the supplied equity.

## Paper trading only
- Simulated positions require a stop loss.
- A risk check prevents a single simulated trade from risking more than 2% of the remaining paper balance.
- Paper positions can be closed manually or monitored against stop/target levels using current ticker marks.
- SQLite stores the paper account state.

**Live order execution is disabled by design.** There is no live order endpoint and no exchange trading credential is required.

## Persistence on hosting
SQLite persistence survives process restarts only when the database file is placed on a persistent mounted volume. Configure:
- `PAPER_DB_PATH=/var/data/paper.sqlite3` (change the directory to the mounted volume path)
- `PAPER_STORAGE_DURABLE=true` only after the hosting volume is mounted and verified.

The current Render blueprint uses the free web-service plan and does not provision a persistent disk. Therefore paper state on that deployment may be lost when its instance is replaced or filesystem is reset. Do not set `PAPER_STORAGE_DURABLE=true` without a persistent volume.

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000.

## API
- `GET /health`
- `GET /api/overview`
- `GET /api/engine/status`
- `GET /api/markets?category=spot|linear`
- `GET /api/scan?category=spot|linear&depth=AUTO|32|64|128|256`
- `GET /api/klines/{symbol}`
- `GET /api/multi-timeframe/{symbol}`
- `GET /api/liquidity/{symbol}`
- `GET /api/flow/{symbol}`
- `GET /api/strategies`
- `GET /api/backtest/{symbol}`
- `POST /api/risk/position-size`
- `GET /api/paper`, `POST /api/paper`
- `POST /api/paper/monitor`
- `POST /api/paper/{trade_id}/close?exit_price=...`

## Tests
Install development requirements and run:
```bash
pip install -r requirements-dev.txt
PYTHONPATH=. pytest -q
```

Historical backtests and signal scores are research tools, not guarantees of future returns or personalized financial advice.


## Simulated trading fees and mark-to-market
- Paper entries and exits include a configurable fee on each side.
- Set `PAPER_FEE_RATE` to a decimal per-side rate (default `0.0006`, or 0.06%).
- The position risk guard includes estimated entry and stop-exit fees within its 2% account risk ceiling.
- `GET /api/paper/summary` marks open positions using current provider ticker prices and reports estimated PnL after fees. If market marks are unavailable, it clearly falls back to each position's entry price.
- A pre-move watch score is surfaced as a research flag, not a guaranteed prediction or entry signal.


## Engine architecture (15 logical modules)
The `GET /api/engines` endpoint exposes the QUANT BRAIN registry and the
implementation state of all 15 logical modules. Status values are conservative:
- `implemented`: a corresponding application capability is wired and testable.
- `partial`: a useful foundation exists, but the listed gaps remain.
- `planned`: no verified production data path is wired yet.

The registry is a capability inventory, not a claim that every proposed engine
is complete. Derivatives analytics (open interest, funding and liquidations),
full market-structure validation, explicit regime classification and
statistically calibrated opportunity probabilities remain on the roadmap.


## Command-driven scanning and entry monitoring
- `GET /api/commands` publishes the transparent command-rule catalogue.
- Select one or more command IDs in the UI; the scanner returns only assets matching at least one selected rule.
- `GET /api/scan?...&command_ids=trend_up,breakout_up` applies selected rules as an OR filter and includes each asset's matching IDs.
- `GET /api/entry-monitor/{symbol}` reports WAITING, APPROACH or CONFIRMED using completed-candle indicator alignment. The UI refreshes the entry status and price/target progress every eight seconds while a symbol is selected.
- Confirmation is informational only. No exchange order is submitted and all trading remains simulation-only.
- Rules include trend alignment, support/resistance proximity, completed-candle breakouts, retest watch, volatility compression, volume expansion/contraction, momentum, RSI extremes, VWAP, MACD, liquidity, and risk/reward filters.
