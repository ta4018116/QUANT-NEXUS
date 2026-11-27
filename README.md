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
is complete. The purple derivatives engine provides Bybit open-interest and funding context
plus a read-only Bybit `allLiquidation` WebSocket proxy for normalized LONG/SHORT
liquidation events and USDT notional. Cross-exchange positioning history remains
unintegrated, so the engine is still correctly marked `partial`. Opportunity
scores are heuristic and are not calibrated win probabilities.


## Command-driven scanning and entry monitoring
- `GET /api/commands` publishes the transparent command-rule catalogue.
- Select one or more command IDs in the UI; the scanner returns only assets matching at least one selected rule.
- `GET /api/scan?...&command_ids=trend_up,breakout_up` applies selected rules as an OR filter and includes each asset's matching IDs.
- `GET /api/entry-monitor/{symbol}` reports WAITING, APPROACH or CONFIRMED using completed-candle indicator alignment. The UI refreshes the entry status and price/target progress every eight seconds while a symbol is selected.
- Confirmation is informational only. No exchange order is submitted and all trading remains simulation-only.
- Rules include trend alignment, support/resistance proximity, completed-candle breakouts, retest watch, volatility compression, volume expansion/contraction, momentum, RSI extremes, VWAP, MACD, liquidity, and risk/reward filters.


## Purple derivatives and liquidation monitor
- `GET /api/derivatives/{symbol}` reports Bybit open interest and funding-rate context for a USDT linear symbol.
- `/ws/derivatives/{symbol}/liquidations` proxies Bybit's public V5 linear `allLiquidation.{symbol}` stream without exchange credentials.
- The central monitoring room displays live liquidation events, liquidated LONG/SHORT notional and a rolling recent-event list for the selected symbol.
- The feed reports executed liquidation prints only; it is not a complete map of positions at risk. The stream is read-only and cannot place orders.
- Live trading remains disabled; all portfolio and order workflows remain simulation-only.

## 156-engine runtime catalogue and early opportunity evaluation
- `GET /api/engine-catalog` returns the canonical 156-entry catalogue split across 12 workstreams. Each entry has an auditable `implemented`, `partial`, or `planned` status.
- `GET /api/engine-suite/coverage` reports callable adapter coverage. A callable adapter is not a claim that every data feed, trained model, or production capability is present.
- `GET /api/engine-suite/{symbol}?category=spot|linear&interval=15m` evaluates the engine suite against one validated market snapshot. The endpoint uses completed candles for signal calculations and obtains optional order-book, trade-flow and 5m/1h/4h context when available.
- `GET /api/early-opportunity/{symbol}?category=spot|linear&interval=15m` returns the same evidence bundle with emphasis on pre-breakout compression, accumulation proxy, volume expansion, order-book imbalance, trade flow, structure and derivatives context.
- Results include explicit missing-input states. News, options, cross-market feeds, model artifacts and full autonomous learning are not fabricated when unavailable.
- The early-opportunity score is a heuristic research score, not a calibrated probability or a guaranteed signal. The entry zone and targets are watch references only; the endpoint never creates a paper order.
- The runtime suite routes all 156 catalogue IDs. Engines requiring unavailable feeds or trained model artifacts return `blocked_missing_input` until their dependencies are integrated and validated.
- Trading mode remains simulation; `live_trading_enabled` is false; no live-order endpoint or exchange trade credential is introduced.

## Market-wide early opportunity scan
- `GET /api/early-opportunity-scan?category=spot&interval=15m&depth=AUTO&max_candidates=256&deep_limit=24`
- Stage 1 checks up to the selected 32/64/128/256/AUTO universe using completed OHLCV candles and a cheap early-setup score.
- Stage 2 deep-checks only the highest-ranked candidates with order-book depth and recent trade prints; linear futures also request funding and open-interest context when available.
- A missing provider result is recorded as a missing confirmation rather than silently treated as positive evidence.
- The endpoint never creates paper or live orders. It returns research watch-ranks and the exact scan/deep-scan counts.

## Runtime feed integrations added

The engine-suite endpoint now attempts read-only public enrichment on each analysis request:
- Provider failover for linear derivatives context (open interest, funding, and account long/short ratio) is fetched for spot and futures symbols where a matching linear contract exists.
- Cross-market correlation uses timestamp-aligned completed candles from a small BTC/ETH/SOL/BNB/XRP peer basket.
- Cross-exchange marks are collected from Bybit, OKX and Binance where reachable. The arbitrage adapter reports gross spread only unless verified round-trip fee and slippage inputs are supplied; it never claims a positive net edge by assuming zero costs.
- Spot-versus-linear prices are sampled to feed basis analysis.
- Public Cointelegraph and CoinDesk RSS headlines are passed to a keyword-triage adapter. This is not fact-checking, and feeds can be unavailable.
- Public Deribit option summaries are used for BTC and ETH only. Greeks/IV are research analytics; dealer-side positioning is not supplied, so net dealer gamma remains unavailable.
- The Twelve Data bridge is exposed at /api/multi-market-engine-suite?market=forex|stocks|indices|commodities&symbol=... and requires TWELVE_DATA_API_KEY to be set as a Render environment variable (never place it in frontend code or chat). It requests time-series OHLCV and returns explicit HTTP 503 until that key is configured.
- Liquidation prints are cached in process memory only while a client is connected to the public liquidation stream. This is not a complete historical liquidation feed.

The provider_health field in the engine-suite response reports each integration's availability. A missing or unsupported source remains explicitly blocked. No source credentials are needed for the public feeds above. Forex, equities, indices and commodities still require a configured dedicated provider such as Twelve Data. No API key has been invented or inserted.

The runtime now supplies paper-ledger, SQLite, process-cache, model-registry, service-health, security-policy and process-memory snapshots where available. The free Render filesystem is not claimed to be durable, no background scheduler/event bus is claimed, and the notification engine creates intents rather than delivering externally. Admin authentication is not enabled and is reported as such by the security engine.

The catalogue still labels approximations and research-only models as partial; changing labels without end-to-end production capability and evidence would be misleading. LSTM/Transformer projection weights are not fully trained, models are not persisted, and no model is calibrated as a production probability. Real trading remains disabled.

## Additional research engines
- A small two-hidden-layer MLP and tabular Q-learning simulator are included as research adapters with chronological holdouts. Neither is a persisted production model, and neither can authorize an order.
- Options analytics calculate Black-Scholes Greeks and implied volatility only when a valid options chain and underlying mark are supplied. Net dealer gamma is omitted unless dealer-side positioning is explicitly supplied.
- LSTM and Transformer now have deterministic research adapters: a fixed-gate recurrent feature extractor and a single-head self-attention feature extractor, each with a trained logistic readout and purged chronological holdout. They are intentionally marked partial because their recurrent/attention projection weights are not end-to-end trained or persisted. The XGBoost-style adapter is a pure-Python research implementation, not the upstream XGBoost library.

- The statistical ML adapters score the latest completed candle for live inference; chronological training and holdout partitions are separate, and all model outputs remain research-only.
- A pure-Python second-order gradient-boosted tree engine is included as an XGBoost-style research implementation. It is not the upstream XGBoost package.
- No catalogue entries are left in the planned state. All 156 IDs have callable runtime adapters. Two sequence-model adapters are research-grade partial implementations with explicit architectural limits; all other partial engines still require the feed or service inputs named in their catalogue gaps.


## Provider, model and operations activation (read-only research)

The provider bridge added in `app/provider_feeds.py` uses:
- Bybit, Binance and OKX public endpoints for crypto candles, tickers, order books, trades and supported linear-derivative snapshots. Access is region-dependent; every provider failure must remain visible in `provider_health`.
- Deribit public BTC/ETH options instruments and book summaries for option-chain analytics. The feed does not disclose dealer-side position signs, so the system must not manufacture net dealer gamma.
- Cointelegraph/CoinDesk RSS plus GDELT DOC 2.0 symbol-filtered article discovery. GDELT and RSS headlines are unverified source material, not fact-checked events. GDELT is rate-limited and cached for five minutes.
- Optional CryptoPanic news, requiring `CRYPTOPANIC_API_TOKEN`.
- Optional CoinGlass one-hour cross-exchange liquidation totals, requiring `COINGLASS_API_KEY`. The Exchange List endpoint returns aggregate USD totals; these totals are not individual liquidation price levels and are never passed off as a price heatmap. The individual Liquidation Orders endpoint requires CoinGlass Standard or higher and is not enabled as a free feed.
- Twelve Data for FX, stocks, indices and commodities, requiring `TWELVE_DATA_API_KEY`.

### Operations API and environment

- `GET /api/provider-health`: reports configured provider families and missing credentials without returning secret values.
- `GET /api/ops/status`: in-process scheduler status, job counters and configured transports.
- `GET /api/models/registry`: lists persisted JSON research-model artifacts.
- `POST /api/models/train/{symbol}?category=spot&interval=15m&limit=500`: trains a logistic research model on completed OHLCV. This route requires the `X-Admin-Token` header matching `MODEL_ADMIN_TOKEN`.
- `GET /health`: includes the background supervisor state.

Optional server-side environment variables (never put these in frontend code):
- `TWELVE_DATA_API_KEY`
- `COINGLASS_API_KEY`
- `CRYPTOPANIC_API_TOKEN`
- `MODEL_ADMIN_TOKEN` (required to enable protected model training)
- `MODEL_REGISTRY_PATH` (defaults to `data/models`)
- `MODEL_REGISTRY_DURABLE=true` only when that path is actually on a persistent mounted disk
- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`, or `ALERT_WEBHOOK_URL`
- `ALERT_DEDUPE_TTL_SECONDS` (defaults to 900)
- `OPS_BACKGROUND_ENABLED=true|false` (defaults to true)
- `OPS_INTERVAL_SECONDS` (defaults to 300; bounded to 60-3600)
- `OPS_WATCHLIST` (defaults to `BTCUSDT,ETHUSDT,SOLUSDT`, maximum 10 valid USDT symbols)

The background scheduler and notification deduplication currently operate inside one web process. They are not a durable distributed worker or a persistent message queue. Hosting platforms that sleep free instances, restart containers or run multiple replicas need an independently deployed worker and persistent database/disk for reliable continuous monitoring. This change does not change the Render plan or claim that a persistent volume has been provisioned.

### Model lifecycle and acceptance criteria

The new persisted logistic candidate uses nine documented OHLCV features, a three-bar label horizon, chronological training/calibration/final-test partitions with purged boundaries, Platt-style calibration, Brier score against a base-rate baseline, log-loss, accuracy and ROC-AUC. Promotion stays `MANUAL_REVIEW_REQUIRED`; passing a research threshold never enables orders.

The random-forest, MLP, LSTM-reservoir, Transformer-reservoir and XGBoost-style adapters remain research implementations; fixed reservoir weights or per-request fitting are not represented as fully trained persisted production models. Model outputs are not investment advice and do not authorize a trade.

All changes preserve `LIVE_TRADING_ENABLED=False`. Public exchange feeds are read-only, no private exchange trade credential is required or added, and all order/position workflows remain simulation-only.

### Per-engine source traceability and honest runtime health

- `GET /api/engine-sources` now returns an explicit source contract for each of the 156 engine IDs: provider families, documented endpoint paths, required evidence, credential model, activation gates and known limitations.
- The registry distinguishes public market feeds, optional paid feeds, internal paper-ledger records, research-model artifacts and process telemetry. A mapped source is not reported as connected until the provider-health and input checks pass.
- The engine source matrix uses the official CoinGlass API v4 endpoint families for derivatives and liquidation data. The aggregate exchange-list liquidation endpoint is not described as a price-level liquidation map; individual liquidation orders and heatmaps are plan-gated.
- Twelve Data remains the configured-provider route for FX, stocks, indices and commodities. Its key must be stored in server environment settings; missing credentials remain a visible blocker.
- Scheduler heartbeat age is now calculated from the last completed job timestamp. A running asyncio task without a completed heartbeat is reported as unknown, not as a fresh heartbeat.
- WebSocket health is marked degraded while liquidation capture remains process-local and lacks an independent durable connection monitor.
- Current CI evidence: the preceding source-registry and 156-engine contract revision passed both repository quality gates and engine-suite validation. The latest heartbeat-truth revision requires its own CI confirmation before merge or deployment.
