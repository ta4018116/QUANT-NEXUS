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


def test_sensitive_engines_have_specific_sources_and_limits():
    registry = engine_source_registry()
    by_id = {item["engine_id"]: item for item in registry["engines"]}
    assert "GDELT DOC 2.0" in by_id["E007"]["providers"]
    assert "CoinGlass /api/futures/liquidation/map" in by_id["E063"]["endpoints"]
    assert "CoinGlass /api/futures/liquidation/orders" in by_id["E064"]["endpoints"]
    assert "Deribit public API for BTC and ETH" in by_id["E069"]["providers"]
    assert "Net dealer gamma must remain unavailable" in by_id["E071"]["limits"]
    assert by_id["E142"]["source_class"] == "event_bus_not_yet_provisioned"
    assert by_id["E145"]["source_class"] == "websocket_stream_runtime"
    assert by_id["E150"]["source_class"] == "notification_delivery_transport"
    assert by_id["E156"]["source_class"] == "real_service_heartbeat_records"
