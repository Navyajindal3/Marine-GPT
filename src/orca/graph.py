from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from orca.state import MarineQueryState

# --- Node Stubs ---

from orca.multilingual import language_node

from orca.planner import planner_node, needs_clarification
from orca.clarification import clarification_node
from orca.supervisor import supervisor_node, route_next_step
from orca.aggregation import aggregation_node

# TODO: Real pause/resume via LangGraph's interrupt + checkpointer needs to be wired in once the serving layer exists.
# For now, clarification_node just sets outgoing_message and the graph proceeds to language node.

def weather_tool_node(state: MarineQueryState) -> MarineQueryState:
    pending = state.get("agents_pending", [])
    if pending:
        agent, day = pending.pop(0)
        state["tool_results"] = state.get("tool_results", {})
        state["tool_results"].setdefault("weather", {})
        state["tool_results"]["weather"][day] = {"wind_kmh": 22, "wave_m": 1.4}
        state.setdefault("agents_called", []).append((agent, day))
    return state

def marine_tool_node(state: MarineQueryState) -> MarineQueryState:
    pending = state.get("agents_pending", [])
    if pending:
        agent, day = pending.pop(0)
        state["tool_results"] = state.get("tool_results", {})
        state["tool_results"].setdefault("marine", {})
        state["tool_results"]["marine"][day] = {"wave_m": 1.5}
        state.setdefault("agents_called", []).append((agent, day))
    return state

def gis_tool_node(state: MarineQueryState) -> MarineQueryState:
    pending = state.get("agents_pending", [])
    if pending:
        agent, day = pending.pop(0)
        state["tool_results"] = state.get("tool_results", {})
        state["tool_results"].setdefault("gis", {})
        state["tool_results"]["gis"][day] = {"distance_from_shore_km": 8.2}
        state.setdefault("agents_called", []).append((agent, day))
    return state

def risk_engine_node(state: MarineQueryState) -> MarineQueryState:
    # Stub: does nothing, just reaches the end
    return state

# --- Edge Routing Functions ---

def route_after_clarification(state: MarineQueryState) -> str:
    if state.get("clarification_resolved_by_cap"):
        return "proceed_to_supervisor"
    return "retry"

# --- Graph Assembly ---

def build_graph():
    graph = StateGraph(MarineQueryState)

    graph.add_node("language", language_node)
    graph.add_node("planner", planner_node)
    graph.add_node("clarification", clarification_node)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("weather_tool", weather_tool_node)
    graph.add_node("marine_tool", marine_tool_node)
    graph.add_node("gis_tool", gis_tool_node)
    graph.add_node("aggregation", aggregation_node)
    graph.add_node("risk_engine", risk_engine_node)

    graph.set_entry_point("language")
    graph.add_edge("language", "planner")

    graph.add_conditional_edges(
        "planner", needs_clarification,
        {
            "clarify_intent": "clarification",
            "clarify_fields": "clarification",
            "proceed": "supervisor",
        }
    )
    
    graph.add_conditional_edges(
        "clarification", route_after_clarification,
        {
            "retry": "language", 
            "proceed_to_supervisor": "supervisor"
        }
    )

    graph.add_conditional_edges(
        "supervisor", route_next_step,
        {
            "call_weather": "weather_tool",
            "call_marine": "marine_tool",
            "call_gis": "gis_tool",
            "aggregate": "aggregation",
            "direct_response": END,
        }
    )
    graph.add_edge("weather_tool", "supervisor")
    graph.add_edge("marine_tool", "supervisor")
    graph.add_edge("gis_tool", "supervisor")
    graph.add_edge("aggregation", "risk_engine")
    graph.add_edge("risk_engine", END)

    memory = MemorySaver()
    app = graph.compile(checkpointer=memory)
    return app

app = build_graph()
