import pytest
from unittest.mock import patch
from orca.graph import app
from orca.state import MarineQueryState

@patch("orca.planner.call_llm_structured")
def test_graph_compiles_and_runs_end_to_end(mock_call_llm):
    mock_call_llm.return_value = {
        "intent": "route_plan",
        "intent_confidence": 0.9,
        "location": {"lat": 12.0, "lng": 74.0},
        "time_window": {"start": "2026-08-31"},
        "vessel_type_raw": "trawler"
    }
    # Canned query state
    initial_state: MarineQueryState = {
        "raw_query": "Is it safe to go fishing tomorrow?"
    }

    # We provide a thread_id for the MemorySaver
    config = {"configurable": {"thread_id": "test_thread_1"}}

    # Run the graph
    # This will invoke the app which is a LangGraph CompiledGraph
    result = app.invoke(initial_state, config=config)

    # Asserts it reaches END without errors by checking the output state
    assert "ready_for_risk_engine" in result
    assert result["ready_for_risk_engine"] is True
    
    assert "aggregated_conditions" in result
    assert "2026-08-31" in result["aggregated_conditions"]

    # Check the flow populated the expected fields
    assert result["intent"] == "route_plan"
    
    # Check that tools were called based on our stubs
    agents_called = [agent for agent, day in result.get("agents_called", [])]
    assert "weather" in agents_called
    assert "marine" in agents_called

@patch("orca.planner.call_llm_structured")
def test_graph_clarification_cap_termination(mock_call_llm):
    # Mock LLM to always return low confidence
    mock_call_llm.return_value = {
        "intent": "route_plan",
        "intent_confidence": 0.5,
        "location": {"lat": 12.0, "lng": 74.0},
        # Deliberately omit time_window to trigger fields transition
        "vessel_type_raw": "trawler"
    }
    
    initial_state: MarineQueryState = {
        "raw_query": "Is it safe to go fishing tomorrow?"
    }
    config = {"configurable": {"thread_id": "test_thread_cap_termination"}}
    
    result = app.invoke(initial_state, config=config)
    
    # Assert graph terminates gracefully
    assert "ready_for_risk_engine" in result
    assert result["ready_for_risk_engine"] is True
    
    # Confirm it hit the cap for intent, transitioned to fields, hit cap for fields, then resolved
    from orca.clarification import MAX_CLARIFICATION_TURNS
    assert result["clarification_turns"] == MAX_CLARIFICATION_TURNS + 2
    assert result["clarification_resolved_by_cap"] is True
    assert result["intent_confidence"] == 1.0  # forced to 1.0 by the cap
    assert "time_window" in result  # Defaulted during the fields cap
