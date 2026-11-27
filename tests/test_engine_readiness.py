from app.engine_catalog import ENGINE_CATALOG
from app.engine_readiness import build_engine_readiness
from app.engine_sources import engine_source_registry


def test_catalogue_status_requires_runtime_pass_and_source_contract():
    source_ids = {row["engine_id"] for row in engine_source_registry()["engines"]}
    assert len(ENGINE_CATALOG) == 156
    assert source_ids == {row["id"] for row in ENGINE_CATALOG}

    suite = {"results": [
        {"engine_id": item["id"], "runtime": {
            "status": "computed" if item["id"] == "E001" else "blocked_missing_input",
            "method": "test fixture",
            "reason": None if item["id"] == "E001" else "missing_feed",
            "missing_inputs": [] if item["id"] == "E001" else ["candles"],
        }}
        for item in ENGINE_CATALOG
    ]}
    readiness = build_engine_readiness(
        suite, market_provider="TEST", provider_health={"derivatives": {"status": "unavailable"}}
    )
    by_id = {item["id"]: item for item in readiness["engines"]}

    assert readiness["total"] == 156
    assert by_id["E001"]["status"] == "implemented"
    assert by_id["E001"]["test_result"]["status"] == "passed"
    assert by_id["E001"]["source_evidence"]["mapped"] is True
    assert by_id["E002"]["status"] == "partial"
    assert by_id["E002"]["test_result"]["status"] == "blocked_or_failed"
    assert any("missing_feed" in reason for reason in by_id["E002"]["readiness_reasons"])
    assert readiness["counts"]["implemented"] == 1
    assert readiness["counts"]["partial"] + readiness["counts"]["planned"] == 155
    assert readiness["live_trading_enabled"] is False


def test_catalogue_partial_never_promotes_from_one_successful_smoke_test():
    partial_id = next(item["id"] for item in ENGINE_CATALOG if item["status"] == "partial")
    planned_id = next((item["id"] for item in ENGINE_CATALOG if item["status"] == "planned"), None)
    suite = {"results": [
        {"engine_id": item["id"], "runtime": {"status": "computed", "method": "fixture"}}
        for item in ENGINE_CATALOG
    ]}
    readiness = build_engine_readiness(suite)
    by_id = {item["id"]: item for item in readiness["engines"]}
    assert by_id[partial_id]["status"] == "partial"
    assert by_id[partial_id]["activation_eligible"] is False
    if planned_id:
        assert by_id[planned_id]["status"] == "planned"
        assert by_id[planned_id]["activation_eligible"] is False


def test_missing_runtime_result_cannot_be_counted_as_implemented():
    suite = {"results": []}
    readiness = build_engine_readiness(suite)
    assert readiness["counts"]["implemented"] == 0
    assert readiness["counts"]["partial"] > 0
    assert all(not item["activation_eligible"] for item in readiness["engines"])
