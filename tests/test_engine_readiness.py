from copy import deepcopy

import app.engine_readiness as readiness_module
from app.engine_catalog import ENGINE_CATALOG
from app.engine_readiness import build_engine_readiness


CHECKED_AT = "2026-11-27T12:00:00+00:00"


def _evidence(engine_id, runtime_status="computed", *, adapter=True, inputs=True):
    return {
        "engine_id": engine_id,
        "checked_at": CHECKED_AT,
        "runtime": {"status": runtime_status, "method": "functional fixture",
                    "reason": None if runtime_status == "computed" else "missing_feed",
                    "missing_inputs": [] if inputs else ["candles"]},
        "adapter_evidence": {"available": adapter, "name": "fixture_adapter" if adapter else None},
        "input_evidence": {"available": inputs, "market_snapshot_valid": inputs,
                           "context_keys_present": ["candles"] if inputs else []},
    }


def _suite(overrides=None):
    overrides = overrides or {}
    return {"results": [overrides.get(item["id"], _evidence(
        item["id"], "blocked_missing_input", inputs=False)) for item in ENGINE_CATALOG]}


def _readiness(suite, *, snapshot=None, health=None):
    return build_engine_readiness(
        suite, market_provider="Bybit",
        provider_health=health or {"market_data": {"status": "ok"}},
        market_snapshot=snapshot or {
            "provider": "Bybit", "source_timestamp": CHECKED_AT,
            "frequency": "intraday", "freshness_status": "fresh", "age_seconds": 30,
        },
    )


def test_all_four_statuses_require_distinct_evidence():
    partial = next(item for item in ENGINE_CATALOG if item["id"] == "E019")
    overrides = {
        "E001": _evidence("E001"),
        partial["id"]: _evidence(partial["id"]),
    }
    suite = _suite(overrides)
    result = _readiness(suite)
    by_id = {item["id"]: item for item in result["engines"]}

    assert by_id["E001"]["status"] == "ACTIVE"
    assert by_id["E001"]["activation_eligible"] is True
    assert by_id["E001"]["source_evidence"]["health_ok"] is True
    assert by_id[partial["id"]]["status"] == "PARTIAL"
    assert by_id[partial["id"]]["activation_eligible"] is False
    assert by_id["E002"]["status"] == "BLOCKED"
    assert by_id["E001"]["last_checked_at"] == CHECKED_AT
    assert result["counts"]["ACTIVE"] + result["counts"]["PARTIAL"] + result["counts"]["BLOCKED"] + result["counts"]["PLANNED"] == 156
    assert result["live_trading_enabled"] is False


def test_stale_source_missing_adapter_or_missing_inputs_cannot_activate():
    invalid_cases = [
        (_evidence("E001"), {"provider": "Bybit", "source_timestamp": CHECKED_AT,
                             "freshness_status": "stale_or_unknown", "frequency": "intraday"},
         {"market_data": {"status": "stale"}}),
        (_evidence("E001", adapter=False), None, None),
        (_evidence("E001", inputs=False), None, None),
    ]
    for evidence, snapshot, health in invalid_cases:
        readiness = _readiness(_suite({"E001": evidence}), snapshot=snapshot, health=health)
        item = next(row for row in readiness["engines"] if row["id"] == "E001")
        assert item["status"] != "ACTIVE"
        assert item["activation_eligible"] is False
        if not evidence["input_evidence"]["available"]:
            assert item["status"] == "BLOCKED"


def test_missing_engine_specific_source_health_blocks_otherwise_computed_adapter():
    result = _readiness(_suite({"E002": _evidence("E002")}))
    item = next(row for row in result["engines"] if row["id"] == "E002")
    assert item["test_result"]["status"] == "passed"
    assert item["status"] == "BLOCKED"
    assert any("مصدر" in reason or "المصدر" in reason for reason in item["readiness_reasons"])


def test_internal_runtime_engine_does_not_require_unrelated_market_snapshot():
    evidence = _evidence("E146")
    evidence["input_evidence"].update({
        "api_heartbeat_fresh": True,
        "heartbeat_records_available": True,
    })
    result = build_engine_readiness(
        _suite({"E146": evidence}),
        provider_health={},
        market_snapshot={},
    )
    item = next(row for row in result["engines"] if row["id"] == "E146")
    assert item["status"] == "ACTIVE"
    assert item["source_evidence"]["market_snapshot_required"] is False
    assert item["source_evidence"]["observed_input"] is True


def test_market_engine_still_requires_a_fresh_timestamped_market_snapshot():
    evidence = _evidence("E001")
    result = build_engine_readiness(
        _suite({"E001": evidence}),
        provider_health={"market_data": {"status": "ok"}},
        market_snapshot={},
    )
    item = next(row for row in result["engines"] if row["id"] == "E001")
    assert item["status"] == "BLOCKED"
    assert item["source_evidence"]["market_snapshot_required"] is True
    assert item["source_evidence"]["observed_input"] is False


def test_paper_position_engines_activate_for_a_verified_empty_ledger():
    from app.engine_suite import run_engine_suite

    ids = ["E103", "E116", "E117", "E125"]
    context = {
        "account": {"equity": 10000},
        "positions": [],
        "current_prices": {},
        "market_snapshot": {"freshness_status": "fresh"},
    }
    suite = run_engine_suite(context, ids)
    result = _readiness(suite)
    by_id = {item["id"]: item for item in result["engines"]}

    for engine_id in ids:
        assert by_id[engine_id]["status"] == "ACTIVE"
        assert by_id[engine_id]["input_evidence"]["paper_positions_known"] is True
        assert by_id[engine_id]["input_evidence"]["open_positions_count"] == 0
        assert by_id[engine_id]["input_evidence"]["position_marks_available"] is True


def test_open_paper_positions_still_require_each_symbol_mark():
    from app.engine_suite import run_engine_suite

    ids = ["E103", "E116", "E117", "E125"]
    context = {
        "account": {"equity": 10000},
        "positions": [{"symbol": "ETHUSDT", "status": "OPEN", "entry": 3000, "quantity": 1}],
        "current_prices": {"BTCUSDT": 90000},
        "market_snapshot": {"freshness_status": "fresh"},
    }
    suite = run_engine_suite(context, ids)
    result = _readiness(suite)
    by_id = {item["id"]: item for item in result["engines"]}

    for engine_id in ids:
        assert by_id[engine_id]["status"] == "BLOCKED"
        assert by_id[engine_id]["input_evidence"]["position_marks_available"] is False
        assert by_id[engine_id]["input_evidence"]["missing_position_mark_symbols"] == ["ETHUSDT"]


def test_live_news_source_can_be_healthy_when_it_returns_no_matching_headlines():
    evidence = _evidence("E007")
    result = _readiness(
        _suite({"E007": evidence}),
        health={
            "market_data": {"status": "ok"},
            "news": {"status": "ok", "event_count": 0},
        },
    )
    item = next(row for row in result["engines"] if row["id"] == "E007")
    assert item["status"] == "ACTIVE"
    assert item["source_evidence"]["health_ok"] is True


def test_orderbook_engines_require_a_recent_observed_snapshot():
    health = {"market_data": {"status": "ok"}, "orderbook": {"status": "ok"}}
    for engine_id in ("E002", "E003"):
        evidence = _evidence(engine_id)
        evidence["input_evidence"].update({
            "orderbook_available": True,
            "orderbook_fresh": True,
        })
        fresh = _readiness(_suite({engine_id: evidence}), health=health)
        fresh_item = next(row for row in fresh["engines"] if row["id"] == engine_id)
        assert fresh_item["status"] == "ACTIVE"

        evidence["input_evidence"]["orderbook_fresh"] = False
        stale = _readiness(_suite({engine_id: evidence}), health=health)
        stale_item = next(row for row in stale["engines"] if row["id"] == engine_id)
        assert stale_item["status"] == "BLOCKED"


def test_multi_timeframe_activation_requires_engine_specific_fresh_frame_evidence():
    evidence = _evidence("E025")
    evidence["input_evidence"]["timeframes_fresh"] = True
    result = _readiness(
        _suite({"E025":evidence}),
        health={"market_data":{"status":"ok"}, "timeframes":{"status":"ok"}},
    )
    row=next(item for item in result["engines"] if item["id"]=="E025")
    assert row["status"]=="ACTIVE"
    evidence["input_evidence"]["timeframes_fresh"] = False
    stale = _readiness(
        _suite({"E025":evidence}),
        health={"market_data":{"status":"ok"}, "timeframes":{"status":"ok"}},
    )
    row=next(item for item in stale["engines"] if item["id"]=="E025")
    assert row["status"]=="BLOCKED"


def test_declared_planned_engine_stays_planned_after_smoke_test(monkeypatch):
    catalog = deepcopy(readiness_module.ENGINE_CATALOG)
    catalog[0]["status"] = "planned"
    monkeypatch.setattr(readiness_module, "ENGINE_CATALOG", catalog)
    result = _readiness(_suite({"E001": _evidence("E001")}))
    item = next(row for row in result["engines"] if row["id"] == "E001")
    assert item["status"] == "PLANNED"
    assert item["activation_eligible"] is False


def test_every_engine_has_adapter_test_source_and_last_check_evidence():
    result = _readiness(_suite({"E001": _evidence("E001")}))
    assert len(result["engines"]) == 156
    for item in result["engines"]:
        assert "adapter_evidence" in item
        assert "input_evidence" in item
        assert "source_evidence" in item
        assert "test_result" in item
        assert "last_checked_at" in item
        assert item["status"] in {"ACTIVE", "PARTIAL", "BLOCKED", "PLANNED"}

