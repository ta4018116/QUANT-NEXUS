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
    assert "Net dealer gamma must remain unavailable" in by_id["E071"]["limitations"]
    assert by_id["E142"]["source_class"] == "sqlite_local_event_log_bus"
    assert by_id["E145"]["source_class"] == "websocket_stream_runtime"
    assert by_id["E150"]["source_class"] == "notification_delivery_transport"
    assert by_id["E156"]["source_class"] == "real_service_heartbeat_records"


def test_noncrypto_market_groups_declare_free_daily_and_optional_twelve_data_sources():
    registry = engine_source_registry()
    by_id = {item["engine_id"]: item for item in registry["engines"]}
    assert "Stooq public daily OHLCV (stocks, indices and supported commodities; no key)" in by_id["E009"]["providers"]
    assert "Frankfurter public daily FX reference rates (no key; close-only)" in by_id["E009"]["providers"]
    assert "Twelve Data optional intraday provider (API key required)" in by_id["E009"]["providers"]
    assert "Stooq /q/d/l/ daily CSV" in by_id["E045"]["endpoints"]
    assert "Frankfurter /{start}..{end} daily reference rates" in by_id["E045"]["endpoints"]
    assert "Twelve_Data_key_optional_for_intraday" in by_id["E101"]["credential_model"]
    assert by_id["E103"]["source_class"] == "paper_position_and_mark_data"
    assert "explicit empty state" in " ".join(by_id["E103"]["required_inputs"])
    assert "Stooq public daily OHLCV (stocks, indices and supported commodities; no key)" not in by_id["E060"]["providers"]


def test_knowledge_memory_and_audit_log_are_not_overstated():
    registry = engine_source_registry()
    by_id = {item["engine_id"]: item for item in registry["engines"]}
    assert by_id["E138"]["source_class"] == "sqlite_opportunity_event_history"
    assert "restart durability depends on a mounted persistent volume" in by_id["E138"]["limitations"]
    assert by_id["E151"]["source_class"] == "append_only_runtime_audit_events"
    assert "every paper-trade mutation and security administration action is not yet covered" in by_id["E151"]["limitations"]

