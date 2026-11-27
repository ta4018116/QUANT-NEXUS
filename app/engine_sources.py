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

def engine_source_registry() -> dict:
    """Return an explicit source contract for every catalogue engine."""
    rows = []
    missing = []
    for engine in ENGINE_CATALOG:
        profile = _PROFILES.get(engine["group"])
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
