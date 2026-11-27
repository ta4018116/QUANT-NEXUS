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
    assert result["counts"]["planned"] > 80
    assert result["counts"]["partial"] >= 45
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


def test_engine_catalog_api_exposes_all_engines_and_paper_only_mode():
    response = TestClient(main.app).get("/api/engine-catalog")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 156
    assert len(payload["engines"]) == 156
    assert payload["live_trading_enabled"] is False
    assert payload["execution_capability"] == "paper_only"
