import pytest
from orca.clarification import (
    generate_intent_disambiguation_question,
    generate_missing_field_question,
    clarification_node,
    MAX_CLARIFICATION_TURNS
)

def test_generate_intent_disambiguation_question():
    state1 = {"intent": "safety_check"}
    assert "Would you like me to check whether it's safe to go fishing" in generate_intent_disambiguation_question(state1)
    
    state2 = {"intent": "conditions_lookup"}
    assert "Would you like me to check whether it's safe to go fishing" in generate_intent_disambiguation_question(state2)
    
    state3 = {"intent": "route_plan"}
    assert "specifically what you'd like to know" in generate_intent_disambiguation_question(state3)

def test_generate_missing_field_question():
    assert "Which location" in generate_missing_field_question("location")
    assert "date or time period" in generate_missing_field_question("time_window")
    assert "type of vessel" in generate_missing_field_question("propulsion_category")
    assert "Could you provide more information about the unknown_field" in generate_missing_field_question("unknown_field")

def test_clarification_node_under_cap():
    state = {
        "clarification_turns": 1,
        "clarification_reason": "intent",
        "intent": "route_plan"
    }
    result = clarification_node(state)
    assert result["clarification_turns"] == 2
    assert result.get("clarification_resolved_by_cap") is not True
    assert "outgoing_message" in result
    assert "specifically what you'd like to know" in result["outgoing_message"]

def test_clarification_node_at_cap_intent():
    state = {
        "clarification_turns": MAX_CLARIFICATION_TURNS,
        "clarification_reason": "intent",
        "intent": "safety_check",
        "intent_confidence": 0.5
    }
    result = clarification_node(state)
    # This will force confidence to 1.0, then compute missing fields
    # safety_check requires "location" and "time_window". Since they are missing, it transitions to fields.
    assert result["clarification_turns"] == MAX_CLARIFICATION_TURNS + 1
    assert result["intent_confidence"] == 1.0
    assert result["clarification_reason"] == "fields"
    assert result["clarification_resolved_by_cap"] is False
    assert result.get("outgoing_message") is not None
    assert "location" in result["missing_fields"]

def test_clarification_node_at_cap_fields():
    state = {
        "clarification_turns": MAX_CLARIFICATION_TURNS,
        "clarification_reason": "fields",
        "missing_fields": ["location", "time_window"]
    }
    result = clarification_node(state)
    assert result["clarification_turns"] == MAX_CLARIFICATION_TURNS + 1
    # time_window gets a default, but location remains missing
    assert result["missing_fields"] == ["location"]
    assert "time_window" in result
    assert result["clarification_reason"] == "fields"
    assert result["clarification_resolved_by_cap"] is False
    assert result.get("outgoing_message") is not None
    
def test_clarification_node_at_cap_fields_time_window_only():
    state = {
        "clarification_turns": MAX_CLARIFICATION_TURNS,
        "clarification_reason": "fields",
        "missing_fields": ["time_window"]
    }
    result = clarification_node(state)
    assert result["clarification_turns"] == MAX_CLARIFICATION_TURNS + 1
    assert result["missing_fields"] == []
    assert "time_window" in result
    assert result["clarification_reason"] is None
    assert result["clarification_resolved_by_cap"] is True
    assert result.get("outgoing_message") is None
