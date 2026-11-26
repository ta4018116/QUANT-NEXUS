# QUANT NEXUS

Standalone multi-market intelligence platform.

## Safety
- Simulation / paper-trading only.
- Live order execution is disabled by design.
- No exchange API secrets are required for the initial demo.

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000.

## Initial scope
- Responsive web application foundation.
- Market overview and watchlist UI.
- Signal-analysis API with explicit demo status.
- Paper portfolio foundation; no live execution.
- Native Android client planned as a separate module.


## Paper account storage and safety

The simulation ledger is written atomically to a JSON file. Configure
`QUANT_NEXUS_STATE_PATH` to point inside a durable mounted volume to preserve
paper trades across deploys. The Render Free web-service filesystem is ephemeral;
local files are lost when the service spins down, restarts, or redeploys. The
app therefore reports `paper_persistence_configured: false` unless
`QUANT_NEXUS_PERSISTENT_STORAGE=true` is explicitly configured by the operator.
Do not treat local-file storage on a Free instance as durable production storage.

Set `PAPER_FEE_RATE` to the simulated per-side fee (default 0.0006). Paper
Futures supports leverage from 1x to 10x. Spot simulation is long-only and 1x.
All live order execution remains disabled.

## Quant research endpoints

- `GET /api/engine/status`: enabled analytical modules and safety state.
- `GET /api/multi-timeframe/{symbol}`: 5m, 15m, 1h, and 4h context.
- `GET /api/strategy/backtest?symbol=BTCUSDT&strategy=ema_cross`: historical EMA cross test.
  `breakout_20` is also supported. Backtests are simplified research simulations
  and are not forecasts of future results.
- `GET /api/paper/summary`: account equity and estimated open-position PnL.
