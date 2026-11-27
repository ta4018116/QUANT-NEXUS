from app.engine_catalog import ENGINE_CATALOG
from app.engine_sources import engine_source_registry


def test_every_catalogue_engine_has_an_explicit_source_contract():
    registry = engine_source_registry()
    assert registry["total_engines"] == 156
    assert registry["mapped_engines"] == 156
    assert registry["unmapped_engine_ids"] == []
    assert registry["source_coverage_pct"] == 100
    ids = [item["engine_id"] for item in registry["engines"]]
    assert len(ids) == len(set(ids)) == len(ENGINE_CATALOG)
    for item in registry["engines"]:
        assert item["providers"]
        assert item["endpoints"]
        assert item["required_inputs"]
        assert item["activation_requires"] == [
            "source_health_ok",
            "fresh_schema_valid_input",
            "engine_specific_test_pass",
        ]
    assert registry["live_trading_enabled"] is False
