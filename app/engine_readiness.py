"""Runtime-derived readiness for the 156-engine catalogue.

Catalogue labels are declarations; dynamic readiness requires a successful
engine execution against a validated runtime snapshot and a mapped source
contract. A callable adapter alone never activates an engine.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .engine_catalog import ENGINE_CATALOG
from .engine_sources import engine_source_registry


# Some engines consume a current market snapshot; others inspect internal
# runtime state. Requiring a market candle for a scheduler, database, or health
# probe would make their readiness depend on an unrelated external feed.
_MARKET_SNAPSHOT_SOURCE_CLASSES = frozenset({
    "market_data", "live_market_snapshot_ingestion", "live_orderbook_depth",
    "orderbook_liquidity_metrics", "ohlcv_realized_volatility", "normalized_ohlcv",
    "ohlcv_data_quality_validation", "news_and_event_discovery",
    "multi_timeframe_market_data", "market_and_microstructure_data",
    "market_data_and_research_artifacts", "derivatives_and_options_data",
    "liquidation_price_map", "observed_liquidation_events", "listed_options_chain",
    "implied_volatility_market_quotes", "options_gamma_exposure",
    "validated_signal_evidence", "portfolio_and_paper_ledger",
    "historical_market_data_and_trade_records", "paper_position_and_mark_data",
    "evidence_fusion",
})


def build_engine_readiness(
    suite: dict,
    *,
    market_provider: str | None = None,
    provider_health: dict | None = None,
    market_snapshot: dict | None = None,
) -> dict:
    source_rows = {
        row["engine_id"]: row
        for row in engine_source_registry().get("engines", [])
    }
    runtime_rows = {
        row.get("engine_id"): row
        for row in suite.get("results", [])
        if row.get("engine_id")
    }
    engines = []
    for catalog in ENGINE_CATALOG:
        engine_id = catalog["id"]
        runtime_row = runtime_rows.get(engine_id, {})
        runtime = runtime_row.get("runtime") or {}
        source = source_rows.get(engine_id)
        runtime_status = runtime.get("status", "not_executed")
        test_passed = runtime_status == "computed"
        source_mapped = bool(source and source.get("providers") and source.get("endpoints"))
        source_health = provider_health or {}
        snapshot = market_snapshot or {}
        adapter = runtime_row.get("adapter_evidence") or {}
        input_evidence = runtime_row.get("input_evidence") or {}
        adapter_available = adapter.get("available") is True
        inputs_available = input_evidence.get("available") is True
        source_class = source.get("source_class") if source else None
        market_snapshot_required = source_class in _MARKET_SNAPSHOT_SOURCE_CLASSES
        snapshot_fresh = (snapshot.get("freshness_status") == "fresh"
                          if market_snapshot_required else True)
        source_health_ok = _source_health_ok(
            source_class,
            source_health,
            market_provider,
            snapshot_fresh,
            input_evidence,
        )
        source_observed = (bool(market_provider and snapshot.get("source_timestamp"))
                           if market_snapshot_required else inputs_available)
        declared = catalog.get("status", "planned")

        if declared == "planned" or not adapter_available:
            dynamic_status = "PLANNED"
        elif (test_passed and inputs_available and source_mapped and source_health_ok
              and source_observed and snapshot_fresh and declared == "implemented"):
            dynamic_status = "ACTIVE"
        elif (runtime_status != "computed" or not inputs_available or not source_mapped
              or not source_health_ok or not source_observed):
            dynamic_status = "BLOCKED"
        else:
            dynamic_status = "PARTIAL"

        reasons = []
        if declared == "planned":
            reasons.append("المحرك مصنف مخططاً ولم يُعتمد للتشغيل.")
        if not adapter_available:
            reasons.append("لا يوجد adapter وظيفي مستقل لهذا المحرك.")
        if not source_mapped:
            reasons.append("لا يوجد عقد مصدر بيانات مكتمل لهذا المحرك.")
        if not inputs_available:
            reasons.append("المدخلات المطلوبة غير مثبتة في لقطة هذا الطلب.")
        if not source_health_ok:
            reasons.append("اتصال المصدر أو صحته لم يثبت لهذا الفحص.")
        if not snapshot_fresh:
            reasons.append("حداثة بيانات المصدر غير مثبتة أو تجاوزت حدها المسموح.")
        if not test_passed:
            reason = runtime.get("reason") or runtime.get("status") or "لم يُنفّذ اختبار تشغيل ناجح"
            reasons.append(f"اختبار التشغيل لم ينجح: {reason}.")
            missing = runtime.get("missing_inputs") or []
            if missing:
                reasons.append("المدخلات الناقصة: " + "، ".join(str(x) for x in missing) + ".")
        if declared == "partial":
            reasons.extend(catalog.get("gaps") or ["توجد فجوات وظيفية موثقة في تعريف المحرك."])
        if declared == "implemented" and dynamic_status != "ACTIVE":
            reasons.append("التصنيف السابق لا يكفي؛ يلزم adapter ومدخلات واختبار ومصدر حديث مثبت.")

        engines.append({
            **catalog,
            "status": dynamic_status,
            "declared_status": declared,
            "test_result": {
                "status": "passed" if test_passed else "blocked_or_failed",
                "runtime_status": runtime_status,
                "method": runtime.get("method"),
                "reason": runtime.get("reason"),
                "missing_inputs": runtime.get("missing_inputs", []),
                "checked_at": runtime_row.get("checked_at"),
            },
            "adapter_evidence": adapter,
            "input_evidence": input_evidence,
            "source_evidence": {
                "mapped": source_mapped,
                "observed_input": source_observed,
                "health_ok": source_health_ok,
                "source_class": source_class,
                "market_snapshot_required": market_snapshot_required,
                "providers": source.get("providers", []) if source else [],
                "endpoints": source.get("endpoints", []) if source else [],
                "market_snapshot_provider": market_provider,
                "market_snapshot": snapshot,
                "provider_health": _redacted_health(source_health),
                "limitations": source.get("limitations") if source else "مصدر غير موثق",
            },
            "readiness_reasons": reasons,
            "last_checked_at": runtime_row.get("checked_at"),
            "activation_eligible": dynamic_status == "ACTIVE",
        })

    statuses = ("ACTIVE", "PARTIAL", "BLOCKED", "PLANNED")
    counts = {status: sum(1 for item in engines if item["status"] == status)
              for status in statuses}
    counts["total"] = len(engines)
    return {
        "total": len(engines),
        "counts": counts,
        "engines": engines,
        "evaluation": "per_request_runtime_execution",
        "last_checked_at": datetime.now(timezone.utc).isoformat(),
        "test_semantics": "ACTIVE requires a dedicated adapter, present inputs, a passing functional run, and healthy observed source evidence. A fresh timestamped market snapshot is required only for market-dependent source classes; internal runtime engines use their own request-time evidence. PARTIAL preserves declared gaps.",
        "trading_mode": "simulation",
        "live_trading_enabled": False,
    }


def _redacted_health(health: dict) -> dict:
    """Keep only safe provider evidence; never echo configuration values."""
    safe = {}
    for key, value in health.items():
        if isinstance(value, dict):
            safe[key] = {
                field: item for field, item in value.items()
                if field in {"status", "provider", "configured_provider", "interval", "freshness", "data_quality", "age_seconds", "reason", "event_count"}
            }
    return safe


def _source_health_ok(source_class, health, market_provider, snapshot_fresh, inputs):
    if not source_class:
        return False
    if source_class not in _MARKET_SNAPSHOT_SOURCE_CLASSES:
        internal_requirements = {
            "sqlite_opportunity_event_history": ("opportunity_history_available",),
            "process_local_scheduler": ("scheduler_jobs_available",),
            "sqlite_local_event_log_bus": ("event_bus_available",),
            "process_local_cache": ("cache_available",),
            "paper_ledger_database": ("database_available",),
            "websocket_stream_runtime": ("websocket_available",),
            "api_gateway_runtime": ("api_heartbeat_fresh",),
            "service_health_probes": ("system_health_available",),
            "structured_error_and_retry_log": ("failure_log_available",),
            "signal_idempotency_store": ("signal_list_available",),
            "notification_delivery_transport": ("notification_transport_available",),
            "append_only_runtime_audit_events": ("audit_log_available",),
            "research_model_artifact_registry": ("model_registry_available",),
            "sqlite_metadata_event_replay": ("replay_log_available",),
            "deployment_security_configuration": ("security_policy_available",),
            "container_resource_telemetry": ("resource_snapshot_available",),
            "real_service_heartbeat_records": ("heartbeat_records_available",),
        }
        required = internal_requirements.get(source_class, ())
        return bool(inputs.get("available") is True and
                    all(inputs.get(key) is True for key in required))
    if not market_provider or not snapshot_fresh:
        return False
    market_health = health.get("market_data") or {}
    if market_health.get("status") not in {"ok", "healthy"}:
        return False
    if source_class in {"market_data", "live_market_snapshot_ingestion", "ohlcv_realized_volatility",
                        "normalized_ohlcv", "ohlcv_data_quality_validation"}:
        return inputs.get("market_snapshot_valid") is True
    requirements = {
        "multi_timeframe_market_data": ("timeframes",),
        "live_orderbook_depth": ("orderbook",),
        "orderbook_liquidity_metrics": ("orderbook",),
        "market_and_microstructure_data": ("orderbook", "trades"),
        "derivatives_and_options_data": ("derivatives", "options"),
        "observed_liquidation_events": ("aggregate_liquidations",),
        "news_and_event_discovery": ("news",),
    }
    signal_requirements = {
        "multi_timeframe_market_data": ("timeframes_fresh",),
        "live_orderbook_depth": ("orderbook_available", "orderbook_fresh"),
        "orderbook_liquidity_metrics": ("orderbook_available", "orderbook_fresh"),
        "market_and_microstructure_data": ("orderbook_available", "orderbook_fresh", "trades_available", "trades_fresh"),
        "validated_signal_evidence": ("entry_confirmation_available",),
        "portfolio_and_paper_ledger": ("portfolio_context_available",),
        "historical_market_data_and_trade_records": ("market_snapshot_valid", "trade_history_available"),
        "paper_position_and_mark_data": ("position_marks_available",),
        "api_gateway_runtime": ("api_heartbeat_fresh",),
        "service_health_probes": ("system_health_ok",),
    }
    required = requirements.get(source_class, ())
    if required and not all((health.get(key) or {}).get("status") in {"ok", "healthy"} for key in required):
        return False
    required_signals = signal_requirements.get(source_class, ())
    if required_signals and not all(inputs.get(key) is True for key in required_signals):
        return False
    return True
