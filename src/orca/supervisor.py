from orca.state import MarineQueryState

INTENT_TO_AGENTS = {
    "safety_check":       ["weather", "marine"],
    "pfz_lookup":         ["marine"],
    "conditions_lookup":  ["weather", "marine"],
    "alert_check":        ["weather"],
    "route_plan":         ["weather", "marine", "gis"],
    "productivity_query": ["marine"],
    "general":            [],
}

INTENT_TO_PIPELINES = {
    "safety_check":       ["risk"],
    "pfz_lookup":         ["risk", "productivity"],
    "conditions_lookup":  [],
    "alert_check":        ["risk"],
    "route_plan":         ["risk", "route_optimization"],
    "productivity_query": ["productivity"],
    "general":            [],
}

def supervisor_node(state: MarineQueryState) -> MarineQueryState:
    # Only compute ONCE. If agents_required is set and non-empty, we skip.
    # If it is empty, recomputing for "general" intent is harmless since it just yields [] again.
    # However, to be perfectly safe against resetting agents_pending, we check if it's already in state.
    if "agents_required" not in state:
        intent = state.get("intent", "general")
        
        agents_required = INTENT_TO_AGENTS.get(intent, [])
        state["agents_required"] = agents_required
        state["pipelines_required"] = INTENT_TO_PIPELINES.get(intent, [])
        state.setdefault("agents_called", [])
        state.setdefault("tool_results", {})
        
        slots = state.get("daily_slots", [])
        if not slots:
            slots = ["single"]
            
        pending = []
        for agent in agents_required:
            if agent == "gis":
                pending.append((agent, "single"))
            else:
                for day in slots:
                    pending.append((agent, day))
                    
        state["agents_pending"] = pending
        
    return state

def route_next_step(state: MarineQueryState) -> str:
    pending = state.get("agents_pending", [])
    if pending:
        next_agent, _ = pending[0]
        return f"call_{next_agent}"
    if not state.get("agents_required"):
        return "direct_response"
    return "aggregate"
