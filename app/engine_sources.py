"""Per-engine source and evidence contracts for the 156-engine catalogue.

This registry distinguishes external market-data feeds from internal runtime
records and model artifacts. A source contract is not proof of connectivity;
provider health and input validation must be checked at runtime.
"""
from __future__ import annotations

from .engine_catalog import ENGINE_CATALOG

_PROFILES = {
    "Market Intelligence": {
        "source_class": "market_data",
        "providers": ["Bybit public V5", "OKX public V5", "Binance public market data"],
        "endpoints": [
            "Bybit /v5/market/kline",
            "Bybit /v5/market/orderbook",
            "Bybit /v5/market/recent-trade",
            "OKX /api/v5/market/candles",
            "OKX /api/v5/market/books",
            "Binance /api/v3/klines or /fapi/v1/klines",
        ],
        "inputs": ["completed OHLCV candles", "timestamped order book", "recent public trades"],
        "credentials": "public_read_only",
        "limits": "Exchange access is region-dependent; each feed must pass freshness and schema checks.",
    },
    "Technical Analysis": {
        "source_class": "market_data",
        "providers": ["Bybit public V5", "OKX public V5", "Binance public market data"],
        "endpoints": [
            "Bybit /v5/market/kline",
            "OKX /api/v5/market/candles",
            "Binance /api/v3/klines or /fapi/v1/klines",
        ],
        "inputs": ["completed OHLCV candles", "volume and timestamp integrity"],
        "credentials": "public_read_only",
        "limits": "Technical indicators are calculations over exchange data, not separate predictive data vendors.",
    },
    "Multi-Timeframe": {
        "source_class": "multi_timeframe_market_data",
        "providers": ["Bybit public V5", "OKX public V5", "Binance public market data"],
        "endpoints": [
            "Bybit /v5/market/kline at each requested interval",
            "OKX /api/v5/market/candles at each requested interval",
            "Binance /api/v3/klines or /fapi/v1/klines",
        ],
        "inputs": ["completed candles for at least two synchronized intervals", "UTC timestamps"],
        "credentials": "public_read_only",
        "limits": "Do not mix incomplete candles or unsynchronized interval boundaries.",
    },
    "Opportunity Hunter": {
        "source_class": "market_and_microstructure_data",
        "providers": ["Bybit public V5", "OKX public V5", "Binance public market data"],
        "endpoints": [
            "Bybit /v5/market/kline",
            "Bybit /v5/market/orderbook",
            "Bybit /v5/market/recent-trade",
            "Bybit /v5/market/funding/history and /v5/market/open-interest for linear contracts",
            "OKX /api/v5/market/candles, /api/v5/market/books, /api/v5/market/trades",
        ],
        "inputs": ["completed OHLCV", "order-book depth", "trade prints", "derivatives context when relevant"],
        "credentials": "public_read_only",
        "limits": "A candidate is not a confirmed breakout; cross-exchange arbitrage requires fees, latency and transfer constraints.",
    },
    "AI Intelligence": {
        "source_class": "market_data_and_research_artifacts",
        "providers": ["Bybit public V5", "OKX public V5", "Binance public market data", "internal JSON model registry"],
        "endpoints": [
            "Bybit /v5/market/kline",
            "OKX /api/v5/market/candles",
            "Binance /api/v3/klines or /fapi/v1/klines",
            "Internal MODEL_REGISTRY_PATH JSON artifacts",
        ],
        "inputs": ["chronological completed OHLCV", "versioned feature schema", "purged train/calibration/test splits", "validated model artifact"],
        "credentials": "public_market_data; protected admin token for training",
        "limits": "A callable ML adapter is not a trained production model; promotion requires holdout evidence and manual review.",
    },
    "Derivatives Intelligence": {
        "source_class": "derivatives_and_options_data",
        "providers": ["Bybit public V5", "OKX public V5", "Binance public futures data", "Deribit public API", "CoinGlass API v4 optional"],
        "endpoints": [
            "Bybit /v5/market/funding/history",
            "Bybit /v5/market/open-interest",
            "Bybit /v5/market/account-ratio",
            "OKX /api/v5/public/funding-rate-history and /api/v5/public/open-interest",
            "Binance /fapi/v1/fundingRate and /fapi/v1/openInterest",
            "Deribit /api/v2/public/get_instruments and /api/v2/public/get_book_summary_by_currency",
            "CoinGlass /api/futures/liquidation/exchange-list (aggregate totals)",
            "CoinGlass /api/futures/liquidation/orders (plan-gated individual events)",
        ],
        "inputs": ["funding rate", "open interest", "long/short ratios", "option chain and underlying mark", "liquidation data with declared granularity"],
        "credentials": "exchange_public_read_only; CoinGlass_API_key_optional_and_plan_gated",
        "limits": "Aggregate liquidation totals are not a price-level heatmap; dealer gamma requires signed dealer positioning and must otherwise remain unavailable.",
    },
    "Opportunity Scoring": {
        "source_class": "validated_signal_evidence",
        "providers": ["Bybit/OKX/Binance market data", "internal opportunity and signal records"],
        "endpoints": [
            "Market-data endpoints listed in Market Intelligence",
            "Internal completed-candle signal context and opportunity records",
        ],
        "inputs": ["computed upstream engine results", "signal timestamps", "entry/stop/target assumptions", "confirmation and expiry state"],
        "credentials": "public_market_data_and_internal_records",
        "limits": "Scores are research ranks, not calibrated win probabilities unless a validated calibration artifact is supplied.",
    },
    "Risk Management": {
        "source_class": "portfolio_and_paper_ledger",
        "providers": ["Internal paper ledger and risk configuration", "Bybit/OKX/Binance public marks"],
        "endpoints": [
            "Internal PaperStore positions, equity, fills and closed-trade records",
            "Bybit /v5/market/tickers",
            "OKX /api/v5/market/ticker",
            "Binance /api/v3/ticker/price or /fapi/v1/ticker/price",
        ],
        "inputs": ["paper equity", "open positions", "exposure by asset", "fees and slippage assumptions", "risk limits", "current marks"],
        "credentials": "internal_paper_records_and_public_read_only_marks",
        "limits": "Never infer account balances or live positions from public feeds; all outputs remain paper-only.",
    },
    "Backtesting & Learning": {
        "source_class": "historical_market_data_and_trade_records",
        "providers": ["Bybit public V5", "OKX public V5", "Binance public market data", "internal paper trade journal"],
        "endpoints": [
            "Bybit /v5/market/kline historical pages",
            "OKX /api/v5/market/history-candles",
            "Binance /api/v3/klines or /fapi/v1/klines",
            "Internal closed paper trades and strategy return series",
        ],
        "inputs": ["chronological OHLCV", "transaction-cost assumptions", "closed trade outcomes", "strict out-of-sample periods"],
        "credentials": "public_read_only_and_internal_paper_records",
        "limits": "Historical simulation must include fees, slippage, survivorship controls and leakage-safe splits.",
    },
    "Trade Management": {
        "source_class": "paper_position_and_mark_data",
        "providers": ["Internal PaperStore and trade journal", "Bybit/OKX/Binance public price feeds"],
        "endpoints": [
            "Internal PaperStore open/closed paper positions",
            "Bybit /v5/market/tickers",
            "OKX /api/v5/market/ticker",
            "Binance /api/v3/ticker/price or /fapi/v1/ticker/price",
        ],
        "inputs": ["paper position lifecycle", "entry/stop/targets", "latest validated mark", "partial-fill simulation state"],
        "credentials": "internal_paper_records_and_public_read_only_marks",
        "limits": "Position monitoring must never call private exchange order or account endpoints.",
    },
    "Multi-Agent Intelligence": {
        "source_class": "evidence_fusion",
        "providers": ["Bybit/OKX/Binance public feeds", "Deribit public options", "GDELT and attributed RSS", "internal engine evidence"],
        "endpoints": [
            "Upstream market, derivatives and news endpoints from their respective source contracts",
            "Internal engine result bus and versioned knowledge store",
        ],
        "inputs": ["timestamped upstream evidence", "source provenance", "engine confidence and missing-input states", "model version"],
        "credentials": "mixed_public_read_only_and_internal",
        "limits": "Agents must not turn missing evidence into consensus; disagreement and provenance must be preserved.",
    },
    "Infrastructure": {
        "source_class": "internal_runtime_telemetry",
        "providers": ["FastAPI runtime", "internal scheduler", "PaperStore/SQLite", "process metrics", "notification transport"],
        "endpoints": [
            "Internal /health and /api/ops/status",
            "Internal scheduler heartbeat and job counters",
            "Internal database, cache, WebSocket, audit and notification telemetry",
            "Linux /proc process metrics where available",
        ],
        "inputs": ["real heartbeat timestamps", "job success/failure counters", "persistent-storage verification", "resource snapshots", "audit records"],
        "credentials": "internal_runtime; notification credentials optional",
        "limits": "An in-process scheduler is not a durable distributed worker; unknown telemetry must remain unknown, not healthy.",
    },
}

_ENGINE_OVERRIDES = {
    "E007": {
        "source_class": "news_and_event_discovery",
        "providers": ["GDELT DOC 2.0", "Cointelegraph RSS", "CoinDesk RSS", "CryptoPanic optional"],
        "endpoints": [
            "GDELT https://api.gdeltproject.org/api/v2/doc/doc",
            "Cointelegraph https://cointelegraph.com/rss",
            "CoinDesk RSS feed",
            "CryptoPanic /api/developer/v2/posts/ (API token required)",
        ],
        "inputs": ["attributed headline", "publisher/source", "publication timestamp", "canonical URL", "asset relevance"],
        "credentials": "GDELT_and_RSS_public; CryptoPanic_token_optional",
        "limits": "Headline discovery and keyword triage only; no source is treated as fact-verified or causal price evidence.",
    },
    "E063": {
        "source_class": "liquidation_price_map",
        "providers": ["CoinGlass API v4 (Professional plan or higher for liquidation maps)", "exchange public liquidation streams for observed events"],
        "endpoints": [
            "CoinGlass /api/futures/liquidation/map",
            "CoinGlass /api/futures/liquidation/aggregated-map",
            "Bybit public linear liquidation WebSocket",
        ],
        "inputs": ["price-bucketed estimated liquidation levels", "map model and timestamp", "underlying mark", "observed liquidation events kept separately"],
        "credentials": "CoinGlass_API_key_and_plan_for_map; public_exchange_stream_for_observed_events",
        "limits": "An aggregate USD liquidation total is not a liquidation heatmap. Modelled liquidation levels must be labelled estimates, not confirmed orders.",
    },
    "E064": {
        "source_class": "observed_liquidation_events",
        "providers": ["Bybit public linear liquidation WebSocket", "CoinGlass API v4 liquidation orders (Standard plan or higher)"],
        "endpoints": [
            "Bybit public linear WebSocket liquidation topic",
            "CoinGlass /api/futures/liquidation/orders",
        ],
        "inputs": ["event timestamp", "symbol", "side", "price", "quantity/notional", "source exchange"],
        "credentials": "public_exchange_stream; CoinGlass_API_key_and_eligible_plan_optional",
        "limits": "The current app's event capture is process-local and only while connected; no complete durable historical event archive is claimed.",
    },
    "E069": {
        "source_class": "listed_options_chain",
        "providers": ["Deribit public API for BTC and ETH", "CoinGlass API v4 options endpoints where plan and instrument coverage permit"],
        "endpoints": [
            "Deribit /api/v2/public/get_instruments",
            "Deribit /api/v2/public/get_book_summary_by_currency",
            "CoinGlass options max-pain and options open-interest endpoints",
        ],
        "inputs": ["option type", "strike", "expiry", "underlying mark", "bid/ask or mark", "open interest", "implied volatility"],
        "credentials": "Deribit_public; CoinGlass_API_key_and_plan_optional",
        "limits": "Current public Deribit integration is BTC/ETH only; no unsupported altcoin chain is fabricated.",
    },
    "E070": {
        "source_class": "implied_volatility_market_quotes",
        "providers": ["Deribit public API for BTC and ETH", "CoinGlass API v4 options history where eligible"],
        "endpoints": [
            "Deribit /api/v2/public/get_book_summary_by_currency",
            "Deribit /api/v2/public/get_instruments",
            "CoinGlass options volatility/open-interest history endpoints",
        ],
        "inputs": ["option bid/ask or mark", "underlying mark", "strike", "time to expiry", "risk-free-rate assumption"],
        "credentials": "Deribit_public; CoinGlass_API_key_and_plan_optional",
        "limits": "IV is solved from observed option prices only when inputs are valid; theoretical volatility is not represented as a market quote.",
    },
    "E071": {
        "source_class": "options_gamma_exposure",
        "providers": ["Deribit public option chain and open interest", "CoinGlass options data where eligible"],
        "endpoints": [
            "Deribit /api/v2/public/get_instruments",
            "Deribit /api/v2/public/get_book_summary_by_currency",
            "CoinGlass options open-interest and volume history endpoints",
        ],
        "inputs": ["option type", "strike", "expiry", "underlying mark", "implied volatility", "open interest", "position-side/dealer sign if genuinely sourced"],
        "credentials": "public_option_market_data; optional paid options data",
        "limits": "Open interest alone does not reveal dealer-side sign. Net dealer gamma must remain unavailable unless signed positioning is sourced.",
    },
    "E141": {
        "source_class": "process_local_scheduler",
        "providers": ["Python asyncio process supervisor"],
        "endpoints": ["Internal BackgroundSupervisor.status()", "Internal scheduler last_started_at and last_finished_at"],
        "inputs": ["actual job start/finish timestamps", "run/failure counters", "task state", "configured interval"],
        "credentials": "none",
        "limits": "Current scheduler is process-local, starts its first scan after the configured interval and is not durable across restarts or multiple replicas.",
    },
    "E142": {
        "source_class": "event_bus_not_yet_provisioned",
        "providers": ["External message broker required for production; no durable broker currently configured"],
        "endpoints": ["Published/consumed counters supplied by a future broker integration"],
        "inputs": ["message ID", "event type", "published/consumed timestamps", "acknowledgement", "retry/dead-letter state"],
        "credentials": "broker_credentials_required_when_selected",
        "limits": "Current adapter can inspect supplied counters but does not create a durable event bus or queue.",
    },
    "E143": {
        "source_class": "process_local_cache",
        "providers": ["In-process TTL cache in provider_feeds.py"],
        "endpoints": ["Internal cache hit/miss/expiry telemetry when exposed"],
        "inputs": ["cache key", "TTL", "insert/read timestamps", "eviction and error counters"],
        "credentials": "none",
        "limits": "Current provider cache is process-local and is not shared or durable across workers.",
    },
    "E144": {
        "source_class": "paper_ledger_database",
        "providers": ["Internal SQLite PaperStore"],
        "endpoints": ["Internal PaperStore load/save and database health"],
        "inputs": ["database path", "transaction outcome", "integrity status", "persistent-volume verification"],
        "credentials": "server_filesystem_permissions",
        "limits": "SQLite persistence is only durable when its path is on an actually mounted persistent volume; an environment flag alone is not proof.",
    },
    "E145": {
        "source_class": "websocket_stream_runtime",
        "providers": ["Bybit public WebSocket feeds", "other exchange public streams where implemented"],
        "endpoints": ["Bybit public linear liquidation stream", "Internal WebSocket connection/task status"],
        "inputs": ["connection state", "last message timestamp", "reconnect count", "subscription state", "capture persistence"],
        "credentials": "public_read_only",
        "limits": "Independent connection monitoring and durable event capture are not currently provisioned; current health must remain degraded.",
    },
    "E146": {
        "source_class": "api_gateway_runtime",
        "providers": ["FastAPI and ASGI server"],
        "endpoints": ["Internal route status", "Internal /health", "HTTP request/error counters when instrumented"],
        "inputs": ["route availability", "HTTP status distribution", "latency", "request IDs"],
        "credentials": "deployment_auth_and_TLS_configuration",
        "limits": "Route registration and a successful health endpoint do not establish authentication or external availability.",
    },
    "E147": {
        "source_class": "service_health_probes",
        "providers": ["FastAPI health endpoint", "provider health checks", "database and scheduler status"],
        "endpoints": ["Internal /health", "Internal /api/provider-health", "Internal /api/ops/status"],
        "inputs": ["real probe result", "last-success timestamp", "failure count", "degraded component state"],
        "credentials": "none_for_local_probes; provider-specific credentials where required",
        "limits": "A health response must report unknown and degraded components rather than treating missing checks as healthy.",
    },
    "E148": {
        "source_class": "structured_error_and_retry_log",
        "providers": ["Application structured logs", "HTTP provider client exceptions"],
        "endpoints": ["Internal request logs and provider failure records"],
        "inputs": ["service", "error class/code", "timestamp", "retry count", "request ID"],
        "credentials": "log_access",
        "limits": "Current adapter classifies supplied failures; it is not a general automatic recovery controller.",
    },
    "E149": {
        "source_class": "signal_idempotency_store",
        "providers": ["Internal signal deduplication keys; durable store required for multi-worker operation"],
        "endpoints": ["Internal notification/signal dedupe cache"],
        "inputs": ["stable signal fingerprint", "symbol", "interval", "event type", "expiry", "persisted idempotency state"],
        "credentials": "none_for_single_process; database_or_cache_credentials_for_shared_store",
        "limits": "Process-local deduplication does not prevent duplicates across restarts or multiple replicas.",
    },
    "E150": {
        "source_class": "notification_delivery_transport",
        "providers": ["Telegram Bot API optional", "Configured HTTPS webhook optional"],
        "endpoints": ["Telegram sendMessage", "Configured HTTPS webhook POST"],
        "inputs": ["validated event type", "dedupe key", "recipient", "delivery result", "retry state"],
        "credentials": "TELEGRAM_BOT_TOKEN_and_TELEGRAM_CHAT_ID_or_ALERT_WEBHOOK_URL",
        "limits": "Delivery is disabled until credentials are configured; delivery attempts and delivery confirmation are distinct states.",
    },
    "E151": {
        "source_class": "audit_event_records",
        "providers": ["Internal paper trade records and structured application audit events"],
        "endpoints": ["Internal PaperStore trade history", "Structured application audit log"],
        "inputs": ["event ID", "actor/service", "action", "timestamp", "before/after reference", "integrity metadata"],
        "credentials": "restricted_server_log_and_database_access",
        "limits": "Current adapter validates supplied audit events; a separate tamper-evident append-only audit store is not provisioned.",
    },
    "E152": {
        "source_class": "research_model_artifact_registry",
        "providers": ["Internal JSON model registry at MODEL_REGISTRY_PATH"],
        "endpoints": ["Internal model registry listing", "Protected POST /api/models/train/{symbol}"],
        "inputs": ["model ID/version", "feature schema", "training/calibration/test ranges", "metrics", "promotion decision", "artifact checksum"],
        "credentials": "MODEL_ADMIN_TOKEN_for_training",
        "limits": "Current persisted logistic model is a research candidate; model promotion remains manual and durable storage requires a verified persistent volume.",
    },
    "E153": {
        "source_class": "historical_event_and_market_replay_store",
        "providers": ["Historical exchange OHLCV APIs", "internal persisted event/trade archive required for event replay"],
        "endpoints": ["Bybit historical klines", "OKX history candles", "Binance klines", "Internal persisted event archive when deployed"],
        "inputs": ["ordered timestamped events", "market data snapshots", "source provenance", "replay cursor"],
        "credentials": "public_read_only_for_market_history; internal_archive_access_for_event_replay",
        "limits": "The adapter sorts supplied events; it does not itself maintain a complete historical event archive.",
    },
    "E154": {
        "source_class": "deployment_security_configuration",
        "providers": ["Server environment configuration", "deployment TLS and secret-management settings"],
        "endpoints": ["Internal security-policy snapshot", "deployment environment and TLS configuration"],
        "inputs": ["paper-only flag", "trade credential presence", "TLS state", "admin authentication state", "secret redaction checks"],
        "credentials": "restricted_environment_metadata_access",
        "limits": "Current adapter checks supplied policy flags; it does not inspect secret values or independently audit the hosting account.",
    },
    "E155": {
        "source_class": "container_resource_telemetry",
        "providers": ["Linux procfs", "container/platform metrics when available"],
        "endpoints": ["/proc/self/statm", "/proc/meminfo", "platform CPU and memory metrics when integrated"],
        "inputs": ["RSS bytes", "memory limit", "CPU usage over a measured interval", "worker count"],
        "credentials": "container_read_only_metrics_access",
        "limits": "Current implementation reads memory from procfs; CPU percentage is intentionally unknown unless measured by a real sampler.",
    },
    "E156": {
        "source_class": "real_service_heartbeat_records",
        "providers": ["FastAPI request heartbeat", "BackgroundSupervisor completed-job timestamps", "future worker heartbeats"],
        "endpoints": ["Internal /health", "Internal /api/ops/status", "last_finished_at timestamps"],
        "inputs": ["service ID", "heartbeat timestamp", "clock source", "expected interval", "last error"],
        "credentials": "internal_runtime_telemetry",
        "limits": "A running task without a completed heartbeat is unknown, not fresh; watchdog reports but does not restart external services.",
    },
}


def engine_source_registry() -> dict:
    """Return an explicit source contract for every catalogue engine."""
    rows = []
    missing = []
    for engine in ENGINE_CATALOG:
        profile = _ENGINE_OVERRIDES.get(engine["id"], _PROFILES.get(engine["group"]))
        if profile is None:
            missing.append(engine["id"])
            continue
        rows.append({
            "engine_id": engine["id"],
            "name": engine["name"],
            "group": engine["group"],
            "catalog_status": engine["status"],
            "source_class": profile["source_class"],
            "providers": list(profile["providers"]),
            "endpoints": list(profile["endpoints"]),
            "required_inputs": list(profile["inputs"]),
            "credential_model": profile["credentials"],
            "limitations": profile["limits"],
            "activation_requires": [
                "source_health_ok",
                "fresh_schema_valid_input",
                "engine_specific_test_pass",
            ],
        })
    return {
        "total_engines": len(ENGINE_CATALOG),
        "mapped_engines": len(rows),
        "unmapped_engine_ids": missing,
        "source_coverage_pct": round(100 * len(rows) / max(1, len(ENGINE_CATALOG)), 2),
        "engines": rows,
        "trading_mode": "simulation",
        "live_trading_enabled": False,
        "disclaimer": "A source contract documents where evidence should come from; it does not claim that optional credentials are configured or that a provider is currently reachable.",
    }
