import pytest
from orca.aggregation import aggregation_node

def test_aggregation_node_multi_day_route_plan():
    state = {
        "daily_slots": ["2026-08-31", "2026-09-01"],
        "tool_results": {
            "weather": {
                "2026-08-31": {"wind_kmh": 22, "wave_m": 1.4},
                "2026-09-01": {"wind_kmh": 25, "wave_m": 1.6}
            },
            "marine": {
                "2026-08-31": {"wave_m": 1.5},
                "2026-09-01": {"wave_m": 1.8}
            },
            "gis": {
                "single": {"distance_from_shore_km": 8.2}
            }
        }
    }
    
    result = aggregation_node(state)
    agg = result["aggregated_conditions"]
    
    # Check shape
    assert len(agg) == 2
    assert "2026-08-31" in agg
    assert "2026-09-01" in agg
    
    # Check day 1
    assert agg["2026-08-31"]["wind_kmph"] == 22
    assert agg["2026-08-31"]["wave_height_m"] == 1.5 # marine takes precedence
    assert agg["2026-08-31"]["distance_from_shore_km"] == 8.2
    assert "chlorophyll" in agg["2026-08-31"]
    assert "sst" in agg["2026-08-31"]
    
    # Check day 2
    assert agg["2026-09-01"]["wind_kmph"] == 25
    assert agg["2026-09-01"]["wave_height_m"] == 1.8
    assert agg["2026-09-01"]["distance_from_shore_km"] == 8.2 # GIS applied to both days
    assert "chlorophyll" in agg["2026-09-01"]
    assert "sst" in agg["2026-09-01"]
    
    assert result["ready_for_risk_engine"] is True

def test_aggregation_node_conditions_lookup():
    # conditions_lookup fetches weather and marine, no gis
    state = {
        "daily_slots": ["2026-08-31"],
        "tool_results": {
            "weather": {
                "2026-08-31": {"wind_kmh": 22, "wave_m": 1.4}
            },
            "marine": {
                "2026-08-31": {"wave_m": 1.5}
            }
        }
    }
    
    result = aggregation_node(state)
    agg = result["aggregated_conditions"]
    
    assert len(agg) == 1
    assert agg["2026-08-31"]["distance_from_shore_km"] is None
    assert agg["2026-08-31"]["wind_kmph"] == 22
    assert "chlorophyll" in agg["2026-08-31"]
    assert "sst" in agg["2026-08-31"]

def test_aggregation_node_empty_edge_case():
    state = {
        "daily_slots": [],
        "tool_results": {}
    }
    
    result = aggregation_node(state)
    agg = result["aggregated_conditions"]
    
    # Defaults to 'single' day since daily_slots is empty
    assert len(agg) == 1
    assert "single" in agg
    assert agg["single"]["wind_kmph"] is None
    assert agg["single"]["wave_height_m"] is None
    assert agg["single"]["distance_from_shore_km"] is None
    assert agg["single"]["chlorophyll"] is None
    assert agg["single"]["sst"] is None
    assert result["ready_for_risk_engine"] is True
