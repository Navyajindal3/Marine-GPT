import pytest
from orca.supervisor import (
    supervisor_node,
    route_next_step,
    INTENT_TO_AGENTS,
    INTENT_TO_PIPELINES
)

def test_supervisor_intents_match_spec():
    # Check that all intents map to the correct agents and pipelines as expected
    for intent, agents in INTENT_TO_AGENTS.items():
        state = {"intent": intent, "daily_slots": ["2026-08-31"]}
        result = supervisor_node(state)
        assert result["agents_required"] == agents
        assert result["pipelines_required"] == INTENT_TO_PIPELINES[intent]
        # Make a fresh state for next iteration
        state = {}

def test_supervisor_agents_pending_count():
    # 3-day route plan
    state = {
        "intent": "route_plan",
        "daily_slots": ["2026-08-31", "2026-09-01", "2026-09-02"]
    }
    result = supervisor_node(state)
    # route_plan requires weather, marine, gis
    # weather * 3, marine * 3, gis * 1 = 7 pairs (3 + 3 + 1)
    assert len(result["agents_pending"]) == 7
    assert ("gis", "single") in result["agents_pending"]
    assert result["agents_pending"].count(("weather", "2026-08-31")) == 1
    assert result["agents_pending"].count(("marine", "2026-09-02")) == 1

def test_supervisor_no_reset_on_reentry():
    state = {
        "intent": "safety_check",
        "daily_slots": ["2026-08-31"]
    }
    result = supervisor_node(state)
    assert len(result["agents_pending"]) == 2
    
    # Simulate tool popping one pending agent
    result["agents_pending"].pop(0)
    assert len(result["agents_pending"]) == 1
    
    # Re-enter supervisor_node
    result2 = supervisor_node(result)
    assert len(result2["agents_pending"]) == 1 # Still 1, didn't reset

def test_supervisor_no_daily_slots():
    # alert_check with no daily_slots
    state = {
        "intent": "alert_check"
    }
    result = supervisor_node(state)
    # Should default to "single"
    assert result["agents_pending"] == [("weather", "single")]

def test_route_next_step():
    state1 = {"agents_pending": [("weather", "2026-08-31")]}
    assert route_next_step(state1) == "call_weather"
    
    # general intent (no agents_required) routes to direct_response
    state2 = {"agents_pending": [], "agents_required": []}
    assert route_next_step(state2) == "direct_response"
    
    # conditions_lookup intent (agents_required, but no pipelines_required) routes to aggregate
    state3 = {"agents_pending": [], "agents_required": ["weather", "marine"], "pipelines_required": []}
    assert route_next_step(state3) == "aggregate"
