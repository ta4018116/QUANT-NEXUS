"""Runtime-derived readiness for the 156-engine catalogue.

Catalogue labels are declarations; dynamic readiness requires a successful
engine execution against a validated runtime snapshot and a mapped source
contract. A callable adapter alone never activates an engine.
"""
from __future__ import annotations

from .engine_catalog import ENGINE_CATALOG
from .engine_sources import engine_source_registry


def build_engine_readiness(
    suite: dict,
    *,
    market_provider: str | None = None,
    provider_health: dict | None = None,
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
        source_observed = test_passed
        declared = catalog.get("status", "planned")

        if declared == "planned":
            dynamic_status = "planned"
        elif declared == "implemented" and test_passed and source_mapped and source_observed:
            dynamic_status = "implemented"
        else:
            dynamic_status = "partial"

        reasons = []
        if declared == "planned":
            reasons.append("المحرك مصنف مخططاً ولم يُعتمد للتشغيل.")
        if not source_mapped:
            reasons.append("لا يوجد عقد مصدر بيانات مكتمل لهذا المحرك.")
        if not test_passed:
            reason = runtime.get("reason") or runtime.get("status") or "لم يُنفّذ اختبار تشغيل ناجح"
            reasons.append(f"اختبار التشغيل لم ينجح: {reason}.")
            missing = runtime.get("missing_inputs") or []
            if missing:
                reasons.append("المدخلات الناقصة: " + "، ".join(str(x) for x in missing) + ".")
        if declared == "partial":
            reasons.extend(catalog.get("gaps") or ["توجد فجوات وظيفية موثقة في تعريف المحرك."])
        if declared == "implemented" and not test_passed:
            reasons.append("التصنيف الثابت لا يكفي؛ لن يُعرض مكتملاً قبل نجاح اختبار التشغيل.")
        if declared == "implemented" and test_passed and not source_mapped:
            reasons.append("نجاح الحساب وحده لا يثبت وجود مصدر بيانات موثق.")

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
            },
            "source_evidence": {
                "mapped": source_mapped,
                "observed_input": source_observed,
                "source_class": source.get("source_class") if source else None,
                "providers": source.get("providers", []) if source else [],
                "endpoints": source.get("endpoints", []) if source else [],
                "market_snapshot_provider": market_provider,
                "provider_health": provider_health or {},
                "limitations": source.get("limitations") if source else "مصدر غير موثق",
            },
            "readiness_reasons": reasons,
            "activation_eligible": bool(
                declared == "implemented" and test_passed and source_mapped and source_observed
            ),
        })

    statuses = ("implemented", "partial", "planned")
    counts = {status: sum(1 for item in engines if item["status"] == status)
              for status in statuses}
    counts["total"] = len(engines)
    return {
        "total": len(engines),
        "counts": counts,
        "engines": engines,
        "evaluation": "per_request_runtime_execution",
        "test_semantics": "A passed result means the engine returned computed output for this validated snapshot; it is not a claim of historical CI coverage or predictive accuracy.",
        "trading_mode": "simulation",
        "live_trading_enabled": False,
    }
