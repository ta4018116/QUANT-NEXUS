from fastapi.testclient import TestClient

from app.main import app


def test_opportunity_room_renders_rich_cards_with_confirmation_and_watch_actions():
    client = TestClient(app)
    response = client.get("/static/monitoring-room.js")
    assert response.status_code == 200
    script = response.text
    assert "qn-opp-details" in script
    assert "turnover24h" in script
    assert "change24h" in script
    assert "entryConfirmation" in script
    assert "button.dataset.oppAction==='analyze'" in script
    assert "button.dataset.oppAction==='remove'" in script
    assert "removeMonitoringSymbol" in script
    assert "live_trading_enabled" not in script or "paper" in script.lower()


def test_opportunity_room_keeps_existing_watchlist_and_paper_only_guard():
    client = TestClient(app)
    room = client.get("/static/monitoring-room.js")
    health = client.get("/health").json()
    assert room.status_code == 200
    assert "quantNexusManualWatchlist" in room.text
    assert "addMonitoringSymbol" in room.text
    assert health["trading_mode"] == "simulation"
    assert health["live_trading_enabled"] is False



def test_monitoring_watchlist_renders_entry_plan_and_animated_progress_cards():
    client = TestClient(app)
    response = client.get("/static/monitoring-room.js")
    assert response.status_code == 200
    script = response.text
    assert "room-watch-card" in script
    assert "دخول مرجعي" in script
    assert "وقف الخسارة" in script
    assert "الهدف الأول" in script
    assert "الهدف الثاني" in script
    assert "room-progress-track" in script
    assert "roomProgressShimmer" in script
    assert "prefers-reduced-motion" in script
