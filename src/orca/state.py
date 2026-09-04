from typing import TypedDict, Optional, Literal

class MarineQueryState(TypedDict, total=False):
    # ---- raw input ----
    raw_query: str
    detected_language: str          # ISO code, e.g. "ml", "hi", "en"
    translated_query: str           # NEW — raw_query translated to English by the
                                     # Multilingual Layer; this is what the Planner
                                     # actually reads, never raw_query directly
    user_id: str
    channel: str                    # "web" | "whatsapp" | "sms" | "call"

    # ---- planner output ----
    intent: Literal[
        "pfz_lookup", "safety_check", "conditions_lookup",
        "alert_check", "route_plan", "productivity_query",
        "general"    # pure conversational/explainer query, e.g. "what is a PFZ?"
    ]
    intent_confidence: float        # NEW — Planner's self-reported confidence in `intent`,
                                     # 0.0-1.0. Gates whether intent is trusted for routing.
    location: Optional[dict]        # {"lat": float, "lng": float, "name": str}
    time_window: Optional[dict]     # {"start": iso_str, "end": iso_str}
    vessel_type_raw: Optional[str]  # exactly what the user said, e.g. "gill netter"
    propulsion_category: Optional[Literal["non_motorized", "motorized", "mechanized"]]
                                     # NORMALIZED — this is what Track 3's Gate 2 lookup
                                     # table actually keys on, not vessel_type_raw
    trip_duration_hours: Optional[int]
    daily_slots: list[str]          # e.g. ["2026-08-31", "2026-09-01", "2026-09-02"]
                                     # derived from time_window + trip_duration_hours —
                                     # one entry per day the trip spans

    # ---- clarification tracking ----
    missing_fields: list[str]
    clarification_reason: Optional[Literal["intent", "fields"]]  # NEW — which kind of
                                     # clarifying question to ask; set by needs_clarification
    clarification_turns: int        # cap at 3 total, covering BOTH reasons combined —
                                     # not one cap per reason, or an ambiguous query could
                                     # loop on "intent" clarification indefinitely
    clarification_resolved_by_cap: bool # NEW — True if we forced resolution to break a loop
    intent_locked: bool             # NEW — True if the cap forced the intent to 1.0
    outgoing_message: Optional[str] # holds the question/response text to surface to the
                                     # user — NOT yet wired to an actual pause/resume mechanism

    # ---- supervisor bookkeeping ----
    agents_required: list[str]      # which of Riddhi's data agents this query needs
    agents_called: list[str]
    agents_pending: list[tuple[str, str]]   # (agent_name, day) pairs — one call per
                                             # agent PER DAY in daily_slots, not per query
    tool_results: dict              # nested by agent, then by day:
                                     # {"weather": {"2026-08-31": {...}, "2026-09-01": {...}},
                                     #  "marine":  {"2026-08-31": {...}, ...},
                                     #  "gis":     {...}}   (GIS is not day-dependent)

    pipelines_required: list[str]   # which of Nandini's engines this query needs:
                                     # subset of ["risk", "productivity", "route_optimization"]
                                     # empty list = pure conversational query, no pipeline at all

    aggregated_conditions: dict     # NEW — output of the Data Aggregation node.
                                     # FLAT per-day structure, exactly what Track 3's Gates 1-5
                                     # expect to read directly, e.g.:
                                     # {"2026-08-31": {
                                     #     "wind_kmph": 22, "wave_height_m": 1.4,
                                     #     "distance_from_shore_km": 8.2, ...
                                     # }, ...}

    # ---- handoff ----
    ready_for_risk_engine: bool
