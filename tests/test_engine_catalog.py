from fastapi.testclient import TestClient

from app import main
from app.engine_catalog import ENGINE_CATALOG, engine_catalog


def test_engine_catalog_contains_exactly_156_unique_engines():
    assert len(ENGINE_CATALOG) == 156
    assert len({item["id"] for item in ENGINE_CATALOG}) == 156
    assert {item["id"] for item in ENGINE_CATALOG} == {
        f"E{index:03d}" for index in range(1, 157)
    }


def test_engine_catalog_statuses_are_auditable_and_conservative():
    result = engine_catalog()
    assert result["total"] == 156
    assert result["counts"]["implemented"] + result["counts"]["partial"] + result["counts"]["planned"] == 156
    assert result["counts"]["planned"] == 0
    assert result["counts"] == {"implemented": 43, "partial": 113, "planned": 0}
    assert all(item["evidence"] != "not_yet_implemented" for item in result["engines"]
               if item["status"] != "planned")
    assert all(item["capabilities"] for item in result["engines"]
               if item["status"] == "implemented")


def test_engine_catalog_preserves_paper_only_safety():
    result = engine_catalog()
    assert result["trading_mode"] == "simulation"
    assert result["live_trading_enabled"] is False
    assert result["execution_capability"] == "paper_only"
    assert result["priority"] == "early_opportunity_detection"


def test_engine_catalog_covers_all_twelve_workstreams():
    result = engine_catalog()
    assert len(result["group_counts"]) == 12
    assert sum(result["group_counts"].values()) == 156


def test_engine_catalog_api_exposes_dynamic_states_and_paper_only_mode(monkeypatch):
    async def fake_suite(symbol, category, interval, limit, request=None):
        readiness = {
            "total":156,
            "counts":{"ACTIVE":1,"PARTIAL":5,"BLOCKED":150,"PLANNED":0,"total":156},
            "engines":[{"id":item["id"],"status":"ACTIVE" if item["id"] == "E001" else "BLOCKED",
                        "declared_status":item["status"],"readiness_reasons":[],"last_checked_at":"2026-11-27T12:00:00+00:00"}
                       for item in ENGINE_CATALOG],
            "last_checked_at":"2026-11-27T12:00:00+00:00","trading_mode":"simulation",
            "live_trading_enabled":False,
        }
        return {"engine_readiness":readiness,"engine_coverage":{},"symbol":symbol,"provider":"Bybit",
                "category":category,"interval":interval,"provider_health":{}}
    monkeypatch.setattr(main, "market_engine_suite", fake_suite)
    response = TestClient(main.app).get("/api/engine-catalog")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 156
    assert len(payload["engines"]) == 156
    assert payload["counts"]["ACTIVE"] == 1
    assert payload["engines"][0]["status"] == "ACTIVE"
    assert payload["engines"][0]["declared_status"] == "implemented"
    assert payload["live_trading_enabled"] is False
    assert payload["execution_capability"] == "paper_only"


def test_engine_suite_coverage_endpoint_returns_dynamic_not_adapter_counts(monkeypatch):
    async def fake_suite(symbol, category, interval, limit, request=None):
        readiness={"total":156,"counts":{"ACTIVE":2,"PARTIAL":4,"BLOCKED":149,"PLANNED":1,"total":156},
                   "engines":[],"last_checked_at":"2026-11-27T12:00:00+00:00",
                   "trading_mode":"simulation","live_trading_enabled":False}
        return {"engine_readiness":readiness,"engine_coverage":{"callable_adapters":156},
                "symbol":symbol,"provider":"Bybit","category":category,"interval":interval,
                "provider_health":{"market_data":{"status":"ok"}}}
    monkeypatch.setattr(main,"market_engine_suite",fake_suite)
    payload=TestClient(main.app).get("/api/engine-suite/coverage").json()
    assert payload["counts"]["ACTIVE"]==2
    assert payload["adapter_coverage"]["callable_adapters"]==156
    assert payload["live_trading_enabled"] is False

