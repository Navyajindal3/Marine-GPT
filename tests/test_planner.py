import pytest
from unittest.mock import patch
from orca.planner import (
    normalize_propulsion,
    compute_daily_slots,
    compute_missing_fields,
    needs_clarification,
    planner_node
)

def test_normalize_propulsion():
    # Known gear name
    state1 = {"vessel_type_raw": " gill netter "}
    assert normalize_propulsion(state1).get("propulsion_category") == "motorized"
    
    # Unknown gear name stays None
    state2 = {"vessel_type_raw": "spaceship"}
    assert normalize_propulsion(state2).get("propulsion_category") is None
    
    # Already present propulsion category is not overwritten
    state3 = {"vessel_type_raw": "trawler", "propulsion_category": "non_motorized"}
    assert normalize_propulsion(state3).get("propulsion_category") == "non_motorized"

def test_compute_daily_slots():
    # Single day
    time_window = {"start": "2026-08-31T10:00:00Z", "end": "2026-08-31T20:00:00Z"}
    slots1 = compute_daily_slots(time_window, trip_duration_hours=10)
    assert slots1 == ["2026-08-31"]
    
    # Multi day (3 days)
    slots2 = compute_daily_slots(time_window, trip_duration_hours=70)
    assert slots2 == ["2026-08-31", "2026-09-01", "2026-09-02"]

def test_compute_missing_fields():
    # Missing fields for route_plan
    state = {"intent": "route_plan"}
    missing = compute_missing_fields(state)
    assert "location" in missing
    assert "time_window" in missing
    assert "propulsion_category" in missing
    
    # Present fields for route_plan
    state2 = {
        "intent": "route_plan",
        "location": {"lat": 12.0, "lng": 74.0},
        "time_window": {"start": "2026-08-31"},
        "propulsion_category": "motorized"
    }
    assert compute_missing_fields(state2) == []

def test_needs_clarification():
    # Low confidence -> clarify_intent
    state1 = {"clarification_reason": "intent"}
    assert needs_clarification(state1) == "clarify_intent"
    
    # Missing fields -> clarify_fields
    state2 = {"clarification_reason": "fields"}
    assert needs_clarification(state2) == "clarify_fields"
    
    # Satisfied -> proceed
    state3 = {"clarification_reason": None}
    assert needs_clarification(state3) == "proceed"
    
    state4 = {}
    assert needs_clarification(state4) == "proceed"

@patch("orca.planner.call_llm_structured")
def test_planner_node_end_to_end(mock_call_llm):
    # Mock the extraction dictionary
    mock_call_llm.return_value = {
        "intent": "route_plan",
        "intent_confidence": 0.9,
        "location": {"lat": 12.0, "lng": 74.0},
        "time_window": {"start": "2026-08-31"},
        "vessel_type_raw": "trawler",
        "trip_duration_hours": 36
    }
    
    state = {
        "translated_query": "I want to take my trawler out for 36 hours",
        "outgoing_message": "Some stale message from previous pass"
    }
    result = planner_node(state)
    
    # Check that normalize_propulsion ran
    assert result["propulsion_category"] == "mechanized"
    
    # Check that compute_daily_slots ran
    assert result["daily_slots"] == ["2026-08-31", "2026-09-01"]
    
    # Check that missing fields was computed properly
    assert result["missing_fields"] == []
    
    # Check clarification_reason was set properly and stale outgoing_message cleared
    assert result["clarification_reason"] is None
    assert result["outgoing_message"] is None

@patch("orca.planner.call_llm_structured")
def test_planner_node_error_fallback(mock_call_llm, caplog):
    # Mock an API error or validation error
    mock_call_llm.side_effect = Exception("Anthropic API Error")
    
    import logging
    state = {"translated_query": "Some query"}
    with caplog.at_level(logging.ERROR):
        result = planner_node(state)
    
    assert result["intent_confidence"] == 0.0
    assert result["clarification_reason"] == "intent"
    assert "Planner LLM failed or failed validation" in caplog.text

@patch("orca.planner.call_llm_structured")
def test_planner_node_preserves_forced_intent(mock_call_llm):
    # Mock LLM returning LOW confidence on a retry pass
    mock_call_llm.return_value = {
        "intent": "route_plan",
        "intent_confidence": 0.3,
        "location": {"lat": 12.0, "lng": 74.0},
        "time_window": {"start": "2026-08-31"},
        "vessel_type_raw": "trawler"
    }
    
    # State simulating re-entry after clarification cap forced intent_confidence to 1.0
    # and transitioned to fields clarification.
    state = {
        "translated_query": "I am going fishing",
        "intent": "safety_check", # Forced intent
        "intent_confidence": 1.0, # Forced confidence
        "intent_locked": True,    # NEW explicitly locked flag
        "clarification_reason": "fields",
        "clarification_turns": 4
    }
    
    result = planner_node(state)
    
    # Assert intent and confidence were preserved despite the LLM returning 0.3 / route_plan
    assert result["intent"] == "safety_check"
    assert result["intent_confidence"] == 1.0
    
    # Assert missing fields was computed for safety_check (which requires location & time_window)
    # Since location and time_window are present in the mock LLM extraction (they got extracted this pass),
    # they will be populated. Wait, safety_check requires location and time_window. 
    # The mock returns location and time_window. So missing_fields will be empty!
    # If missing_fields is empty, clarification_reason will correctly resolve to None.
    # Let's verify that's the case.
    assert result["missing_fields"] == []
    assert result["clarification_reason"] is None

@patch("orca.planner.call_llm_structured")
def test_planner_node_intent_not_locked_if_confident_first_pass(mock_call_llm):
    # Mock LLM returning LOW confidence and different intent on a retry pass
    mock_call_llm.return_value = {
        "intent": "route_plan",
        "intent_confidence": 0.4,
        "location": {"lat": 12.0, "lng": 74.0},
        "time_window": {"start": "2026-08-31"},
        "vessel_type_raw": "trawler"
    }
    
    # State simulating re-entry after a NATURALLY confident first pass that was missing fields
    state = {
        "translated_query": "I am going fishing",
        "intent": "safety_check", 
        "intent_confidence": 1.0, # Was originally naturally confident
        # intent_locked is NOT set (so it's False)
        "clarification_reason": "fields",
        "clarification_turns": 1
    }
    
    result = planner_node(state)
    
    # Assert intent and confidence were OVERWRITTEN because it wasn't locked
    assert result["intent"] == "route_plan"
    assert result["intent_confidence"] == 0.4
    assert result["clarification_reason"] == "intent"

@patch("orca.planner.call_llm_structured")
def test_planner_node_merges_non_none(mock_call_llm):
    # Mock LLM returning None for location
    mock_call_llm.return_value = {
        "intent": "route_plan",
        "intent_confidence": 0.9,
        "location": None,  # Simulated non-mention
        "time_window": {"start": "2026-08-31"}
    }
    
    state = {
        "translated_query": "I want to go fishing",
        "location": {"lat": 15.0, "lng": 73.0, "name": "Goa"} # Pre-existing location
    }
    
    result = planner_node(state)
    
    # Assert location was NOT overwritten by None
    assert result["location"] == {"lat": 15.0, "lng": 73.0, "name": "Goa"}


