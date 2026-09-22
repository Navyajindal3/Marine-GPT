# tests/test_maps.py - map images + risk-chip helpers (kochi/mapgen).
import os
import sys

import kochi


def test_risk_score_format():
    for cat in ("non_motorized", "motorized", "mechanized"):
        score, chip = kochi.risk_score(cat, 2, "en")
        assert 0 <= score <= 100
        assert chip.startswith(f"{score}/100")


def test_risk_score_hindi():
    _, chip = kochi.risk_score("mechanized", 3, "hi")
    assert "/100" in chip


def test_fishing_potential():
    zone = {"chl": 5.9}
    assert kochi.fishing_potential(zone) == "High"
    assert kochi.fishing_potential({"chl": 2.2}) == "Low"


def test_mapgen_renders_route_map_unavailable_offline(monkeypatch):
    """Maps must degrade to None/empty captions when tiles are unavailable."""
    import mapgen

    def _no_tiles(*a, **k):
        return None
    monkeypatch.setattr(mapgen, "_fetch_tiles", _no_tiles)
    zone = kochi.select_zone("mechanized", 2, 2)
    path, caption = mapgen.render_route_map(zone)
    assert path and os.path.exists(path) and caption


def test_mapgen_avoid_map(monkeypatch):
    import mapgen
    monkeypatch.setattr(mapgen, "_fetch_tiles", lambda *a, **k: None)
    path, caption = mapgen.render_avoid_map()
    assert path and os.path.exists(path) and "R1" in mapgen.RESTRICTED_AREAS[0]


def test_router_marks_map_kind_for_route():
    import router
    b = router.Router()
    b.handle("m1", "pfz")
    b.handle("m1", "2 days trawler")
    b.handle("m1", "route")
    kind, zone, day = b.map_context("m1")
    assert kind == "route" and zone is not None
    # consumed once
    assert b.map_context("m1") == (None, None, None)


# ---- regression: a 6-day trip must show ALL 6 days, not just 3 ---------------
def test_six_day_trip_shows_all_six_days():
    r = kochi.answer_safety("vallam", trip_days=6, day=1, lang="en")
    for n in range(1, 7):
        assert f"Day {n} (" in r
    assert "Day 7 (" not in r


def test_six_day_trip_via_router_dialogue():
    import router
    b = router.Router()
    b.handle("m2", "is it safe to go to sea tomorrow")
    r = b.handle("m2", "6 days vallam")
    for n in range(1, 7):
        assert f"Day {n} (" in r
    assert "6-day trip" in r and "vallam" in r


def test_trip_longer_than_forecast_week_gets_note():
    r = kochi.answer_safety("trawler", trip_days=10, day=1, lang="en")
    assert "Day 7 (" in r                    # full forecast week shown
    assert "beyond the 7-day forecast" in r  # and an honest horizon note


def test_forecast_table_is_a_full_week():
    assert max(kochi.FORECASTS) >= 7
    for d in range(1, 8):
        assert {"wave_m", "wind_kmph", "vis_km", "sea", "note"} <= set(
            kochi.FORECASTS[d])
