from datetime import datetime, timedelta, timezone
from orca.state import MarineQueryState
from orca.planner import compute_missing_fields

# MAX_CLARIFICATION_TURNS needs tuning later per the plan
MAX_CLARIFICATION_TURNS = 3

def generate_intent_disambiguation_question(state: MarineQueryState) -> str:
    intent = state.get("intent")
    # For commonly-confused intent pairs (e.g. safety_check vs conditions_lookup)
    if intent in ("safety_check", "conditions_lookup"):
        return "Would you like me to check whether it's safe to go fishing, or would you like the marine conditions for tomorrow?"
    
    # Fallback generic question
    return "Could you tell me more specifically what you'd like to know?"

def generate_missing_field_question(field: str) -> str:
    templates = {
        "location": "Which location or area are you asking about?",
        "time_window": "For what date or time period are you asking?",
        "propulsion_category": "What type of vessel or propulsion are you using?"
    }
    return templates.get(field, f"Could you provide more information about the {field}?")

def clarification_node(state: MarineQueryState) -> MarineQueryState:
    turns = state.get("clarification_turns", 0) + 1
    state["clarification_turns"] = turns
    
    if turns > MAX_CLARIFICATION_TURNS:
        reason = state.get("clarification_reason")
        if reason == "intent":
            state["intent_confidence"] = 1.0
            state["intent_locked"] = True
            missing = compute_missing_fields(state)
            if missing:
                state["missing_fields"] = missing
                state["clarification_reason"] = "fields"
                state["clarification_resolved_by_cap"] = False
                state["outgoing_message"] = generate_missing_field_question(missing[0])
            else:
                state["clarification_reason"] = None
                state["clarification_resolved_by_cap"] = True
                state["outgoing_message"] = None
            return state
            
        elif reason == "fields":
            missing = state.get("missing_fields", [])
            still_missing = []
            for field in missing:
                if field == "time_window":
                    now = datetime.now(timezone.utc)
                    state["time_window"] = {
                        "start": now.isoformat(),
                        "end": (now + timedelta(hours=12)).isoformat()
                    }
                elif field == "location":
                    still_missing.append(field)
                    
            if "location" in still_missing:
                state["missing_fields"] = still_missing
                state["clarification_reason"] = "fields"
                state["clarification_resolved_by_cap"] = False
                state["outgoing_message"] = generate_missing_field_question("location")
            else:
                state["missing_fields"] = []
                state["clarification_reason"] = None
                state["clarification_resolved_by_cap"] = True
                state["outgoing_message"] = None
            return state
        
    reason = state.get("clarification_reason")
    if reason == "intent":
        state["outgoing_message"] = generate_intent_disambiguation_question(state)
        state["clarification_resolved_by_cap"] = False
    elif reason == "fields":
        missing = state.get("missing_fields", [])
        if missing:
            state["outgoing_message"] = generate_missing_field_question(missing[0])
            state["clarification_resolved_by_cap"] = False
            
    return state
