import os
import math
from datetime import timedelta, datetime
from typing import Optional, Literal
import logging
import anthropic
from pydantic import BaseModel, Field, ValidationError
from orca.state import MarineQueryState

# Module-level constants
INTENT_THRESHOLD = 0.7  # Needs tuning per the plan
logger = logging.getLogger(__name__)

# Schema definition for Planner LLM output
class PlannerExtractionSchema(BaseModel):
    intent: Literal[
        "pfz_lookup", "safety_check", "conditions_lookup",
        "alert_check", "route_plan", "productivity_query",
        "general"
    ] = Field(description="The primary intent of the user's query.")
    intent_confidence: float = Field(
        description="Confidence in the intent classification (0.0 to 1.0)."
    )
    location: Optional[dict] = Field(
        default=None, 
        description="Location information, e.g. {'lat': 12.9, 'lng': 74.8, 'name': 'Mangalore'}"
    )
    time_window: Optional[dict] = Field(
        default=None, 
        description="Time window for the query, e.g. {'start': '2026-08-31', 'end': '2026-09-02'}"
    )
    vessel_type_raw: Optional[str] = Field(
        default=None, 
        description="The exact vessel or gear type mentioned by the user."
    )
    propulsion_category: Optional[Literal["non_motorized", "motorized", "mechanized"]] = Field(
        default=None, 
        description="The normalized propulsion category if it can be inferred."
    )
    trip_duration_hours: Optional[int] = Field(
        default=None, 
        description="The expected duration of the trip in hours."
    )

PLANNER_PROMPT = """You are a routing planner for a marine intelligence platform.
Your job is to read the translated English query and extract structured fields.
Do not provide safety reasoning or attempt to answer the user's query.

Extract the following:
1. intent: Must be one of ["pfz_lookup", "safety_check", "conditions_lookup", "alert_check", "route_plan", "productivity_query", "general"].
2. intent_confidence: A float between 0.0 and 1.0 indicating your confidence in the intent. 
   CRITICAL: Use a LOWER score when the query could plausibly fit more than one intent 
   (e.g. "Is it safe to go fishing tomorrow?" could be safety_check or conditions_lookup). 
   Defaulting to 1.0 for ambiguous queries is unsafe.
3. location: If mentioned, extract lat, lng, and name.
4. time_window: If mentioned, extract start and end ISO dates.
5. vessel_type_raw: The exact boat or gear name mentioned.
6. propulsion_category: Infer if it is "non_motorized", "motorized", or "mechanized".
7. trip_duration_hours: The trip duration in hours, if mentioned.
"""

def call_llm_structured(prompt: str, input_text: str, schema: type[BaseModel]) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key == "your_anthropic_api_key_here":
        raise ValueError("ANTHROPIC_API_KEY not configured")
        
    client = anthropic.Anthropic(api_key=api_key)
    
    # Use Anthropic tools API to force structured output
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=prompt,
        messages=[{"role": "user", "content": input_text}],
        tools=[{
            "name": "extract_fields",
            "description": "Extract structured fields from the marine query.",
            "input_schema": schema.model_json_schema()
        }],
        tool_choice={"type": "tool", "name": "extract_fields"}
    )
    
    # Extract the tool use arguments
    for block in response.content:
        if block.type == "tool_use" and block.name == "extract_fields":
            return schema(**block.input).model_dump()
            
    raise ValueError("No extract_fields tool call found in LLM response.")

GEAR_TO_PROPULSION = {
    "canoe": "non_motorized", 
    "country boat": "non_motorized",
    "gill netter": "motorized", 
    "outboard": "motorized",
    "trawler": "mechanized", 
    "purse seiner": "mechanized",
}

def normalize_propulsion(state: MarineQueryState) -> MarineQueryState:
    if not state.get("propulsion_category") and state.get("vessel_type_raw"):
        key = state["vessel_type_raw"].strip().lower()
        state["propulsion_category"] = GEAR_TO_PROPULSION.get(key)
    return state

def compute_daily_slots(time_window: dict, trip_duration_hours: int) -> list[str]:
    try:
        # Replace 'Z' with '+00:00' to support older ISO string formats if necessary, 
        # though Python 3.11+ fromisoformat handles 'Z'.
        start_str = time_window.get("start", "")
        if start_str.endswith("Z"):
            start_str = start_str[:-1] + "+00:00"
        start = datetime.fromisoformat(start_str)
    except Exception:
        # Fallback if unparseable
        return []
    
    num_days = max(1, math.ceil(trip_duration_hours / 24))
    return [(start + timedelta(days=i)).date().isoformat() for i in range(num_days)]

REQUIRED_FIELDS = {
    "safety_check": ["location", "time_window"],
    "pfz_lookup": ["location"],
    "route_plan": ["location", "time_window", "propulsion_category"],
    "alert_check": ["location"],
}

def compute_missing_fields(state: MarineQueryState) -> list[str]:
    required = REQUIRED_FIELDS.get(state.get("intent"), [])
    return [f for f in required if not state.get(f)]

def planner_node(state: MarineQueryState) -> MarineQueryState:
    translated_query = state.get("translated_query", "")
    
    try:
        extracted = call_llm_structured(
            prompt=PLANNER_PROMPT,
            input_text=translated_query,
            schema=PlannerExtractionSchema
        )
    except Exception as e:
        logger.error(f"Planner LLM failed or failed validation: {e}")
        extracted = {"intent_confidence": 0.0}
        
    # PRESERVE forced intent if it was capped
    if state.get("intent_locked"):
        extracted["intent_confidence"] = 1.0
        if "intent" in state:
            extracted["intent"] = state["intent"]
        
    state.update({k: v for k, v in extracted.items() if v is not None})
    state = normalize_propulsion(state)
    
    if state.get("time_window"):
        state["daily_slots"] = compute_daily_slots(
            state["time_window"], 
            state.get("trip_duration_hours") or 24
        )
        
    if state.get("intent_confidence", 0) >= INTENT_THRESHOLD:
        state["missing_fields"] = compute_missing_fields(state)
    else:
        state["missing_fields"] = []
        
    # Set clarification reason securely within the node
    if state.get("intent_confidence", 0) < INTENT_THRESHOLD:
        state["clarification_reason"] = "intent"
    elif state.get("missing_fields"):
        state["clarification_reason"] = "fields"
    else:
        state["clarification_reason"] = None
        state["outgoing_message"] = None
        
    return state

def needs_clarification(state: MarineQueryState) -> str:
    reason = state.get("clarification_reason")
    if reason == "intent":
        return "clarify_intent"
    if reason == "fields":
        return "clarify_fields"
    return "proceed"
