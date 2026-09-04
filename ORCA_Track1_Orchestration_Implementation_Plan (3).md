# ORCA — Track 1: Orchestration & State Management ("The Brain")
### Full Implementation Plan — Owner: Navya

---

## 0. Scope: what Track 1 actually owns

Everything that happens **before** the Risk Engine touches the query, now expanded to include two pieces that were previously flagged as unowned. Concretely:

- Turning a raw user message (in **any language**, from any future channel) into a fully-structured, validated state object
- **Detecting and translating the query's language**, and providing the reverse-translation utility the Explanation Agent needs at the end (Section 3)
- Deciding what's missing and asking for it
- Deciding which of Riddhi's data agents (Weather / Marine / GIS) need to be called for this specific query
- **Flattening Riddhi's nested per-agent, per-day results into the single flat structure Nandini's Risk Engine expects** (Section 7)
- Knowing when enough data has been gathered to hand off to Nandini's Risk Engine

Track 1 does **not** own: fetching real data (Track 2), computing risk/productivity scores (Track 3), or the final natural-language response (Track 3's Explanation Agent) — though that agent calls a translation function you own. Your job ends the moment the state is complete and handed off.

This means your single most valuable deliverable to the team isn't code — it's the **shared state schema**, because it's the contract every other track codes against.

---

## 1. Shared State Schema (build and circulate this FIRST)

Lock this with Riddhi and Nandini before writing real node logic. Bikeshedding key names later costs days.

```python
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
```

**Why `total=False`:** the state is populated gradually across nodes — nothing should assume every key exists at every point.

**Why this matters for integration:** Riddhi's tool functions should take arguments derived *only* from this schema (e.g. `lat`, `lng`, a single `day`) and write their output into `tool_results[<agent_name>][<day>]`. Nandini's Risk Engine should expect nothing except a state object where `ready_for_risk_engine == True` and `aggregated_conditions` is populated and flat. Neither of them should ever need to look inside your node code.

**Two fields worth calling out explicitly**, since they came out of reviewing this against Track 3's spec directly:
- `propulsion_category` exists *only* because Track 3's Gate 2 lookup table is keyed by propulsion category (`non_motorized` / `motorized` / `mechanized`), not by whatever gear name the fisherman actually says. This is a normalization step Track 1 owns — see Section 4.
- `distance_from_shore_km` isn't its own top-level field — it's produced by Riddhi's GIS tool and lands inside `aggregated_conditions[<day>]` once the aggregation step (Section 6) runs. It needs to exist as an explicit key in the aggregation output, not be assumed.

---

## 2. LangGraph skeleton (build this second, with everything else stubbed)

Get the *shape* of the graph running end-to-end before any node has real logic. This is the highest-leverage thing you can do in week one — it proves the architecture and gives Riddhi/Nandini a live target to plug into.

```python
from langgraph.graph import StateGraph, END

graph = StateGraph(MarineQueryState)

graph.add_node("language", language_node)           # NEW — Multilingual Layer, see Section 3
graph.add_node("planner", planner_node)
graph.add_node("clarification", clarification_node)
graph.add_node("supervisor", supervisor_node)
graph.add_node("weather_tool", weather_tool_node)   # Riddhi's, stubbed for now
graph.add_node("marine_tool", marine_tool_node)     # Riddhi's, stubbed for now
graph.add_node("gis_tool", gis_tool_node)           # Riddhi's, stubbed for now
graph.add_node("aggregation", aggregation_node)     # NEW — see Section 7
graph.add_node("risk_engine", risk_engine_node)     # Nandini's, stubbed for now

graph.set_entry_point("language")
graph.add_edge("language", "planner")

graph.add_conditional_edges(
    "planner", needs_clarification,
    {
        "clarify_intent": "clarification",   # low intent_confidence
        "clarify_fields": "clarification",   # intent trusted, but a required field is missing
        "proceed": "supervisor",
    }
)
graph.add_edge("clarification", "language")  # NOT "planner" directly — re-detect/translate,
                                              # since a user could reply in a different
                                              # language than their original query

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

app = graph.compile()
```

Stub every non-Track-1 node with something like:

```python
def weather_tool_node(state: MarineQueryState) -> MarineQueryState:
    agent, day = state["agents_pending"].pop(0)   # e.g. ("weather", "2026-08-31")
    state["tool_results"].setdefault("weather", {})
    state["tool_results"]["weather"][day] = {"wind_kmh": 22, "wave_m": 1.4}  # fake, realistic
    state["agents_called"].append((agent, day))
    return state
```

Swap these for Riddhi's real functions later — nothing else in your graph should need to change if the schema contract holds.

---

## 3. Multilingual Layer (Language Detection + Translation) — now owned by you

**The gap this closes:** this was previously flagged as unowned. It sits as its own node, right before the Planner — the Planner should only ever work in English, never on raw multilingual text. This keeps the Planner's prompt simple and means Riddhi's/Nandini's code never has to think about language at all.

**What it does, in order:**
1. **Detect the language** — `langdetect` as a fast first pass on `raw_query`.
2. **Translate to English** — call a translation API, store the result in `translated_query`. `raw_query` itself is left untouched (you still need the original for logging/debugging, and potentially for the reverse-translation step to sanity-check tone).
3. Everything downstream (Planner onward) reads `translated_query`, never `raw_query`.

**Which translation API — decision, not left implicit:** use **Bhashini** (Government of India's translation API) as primary, since your problem statement explicitly emphasizes Indian regional language support and it's purpose-built for Indian languages rather than general-purpose. Fall back to **Google Cloud Translate** if a Bhashini call fails or times out — don't let a translation API outage take down the whole pipeline.

```python
import langdetect

def detect_language_fast(text: str) -> str:
    try:
        return langdetect.detect(text)
    except langdetect.lang_detect_exception.LangDetectException:
        return "en"  # empty/too-short text — assume English rather than fail

def translate_text(text: str, source_lang: str, target_lang: str) -> str:
    if source_lang == target_lang:
        return text
    try:
        return bhashini_translate(text, source_lang, target_lang)   # primary
    except (TimeoutError, ConnectionError) as e:
        log_translation_fallback(e)
        return google_translate(text, source_lang, target_lang)     # fallback

def language_node(state: MarineQueryState) -> MarineQueryState:
    lang = detect_language_fast(state["raw_query"])
    state["detected_language"] = lang
    state["translated_query"] = translate_text(state["raw_query"], lang, "en")
    return state
```

**Reverse translation — a shared utility you own, called by Track 3's Explanation Agent:** since you're already building the Bhashini/Google Translate wrapper, expose it as a reusable function so Nandini's Explanation Agent doesn't duplicate the API integration:

```python
def translate_response(text: str, target_lang: str) -> str:
    return translate_text(text, source_lang="en", target_lang=target_lang)
```

Hand this function (not raw API credentials) to Nandini once it's built — she calls `translate_response(explanation_text, state["detected_language"])` at the very end of her Explanation Agent.

**One thing worth deciding with the team, since it affects the clarification loop:** the graph now routes `clarification → language → planner` rather than straight back to `planner` (Section 2), because a user's reply to a clarifying question could itself be in a different language, or mix regional words with English — re-running language detection on every turn is safer than assuming it stays constant.

---

## 4. Planner Agent

**Job:** one LLM call that converts free text into structured fields — never raw text passed downstream.

Implementation notes:
- Use structured/JSON-mode output (function-calling schema matching `MarineQueryState`'s planner fields), not "ask the LLM to write JSON in a text prompt and hope."
- **Language is no longer this node's concern.** By the time the Planner runs, the Multilingual Layer (Section 3) has already populated `translated_query` with an English version — the Planner reads `translated_query`, not `raw_query`, and never sees the original language at all. This keeps the Planner's prompt simpler than earlier drafts of this plan assumed.
- Keep the prompt narrow: extract intent + slots only. Don't let the planner try to reason about safety or produce recommendations — that's not its job and blurs ownership.

**Vessel propulsion normalization (new — closes a real gap against Track 3's spec):** Track 3's Gate 2 lookup table is keyed by `propulsion_category` (`non_motorized` / `motorized` / `mechanized`), but a fisherman will say "gill netter," "trawler," "canoe" — gear or boat names, not propulsion categories. Two-layer approach, decided so this isn't left as an assumption:
1. **Primary:** ask the Planner's structured-extraction schema for `propulsion_category` directly, not just `vessel_type_raw` — the LLM can usually infer propulsion from common boat/gear names on its own.
2. **Fallback:** a small deterministic mapping table normalizes anything the LLM leaves ambiguous, as a safety net rather than the primary mechanism:

```python
GEAR_TO_PROPULSION = {
    "canoe": "non_motorized", "country boat": "non_motorized",
    "gill netter": "motorized", "outboard": "motorized",
    "trawler": "mechanized", "purse seiner": "mechanized",
    # ... extend with team input, this is a starting set
}

def normalize_propulsion(state: MarineQueryState) -> MarineQueryState:
    if not state.get("propulsion_category") and state.get("vessel_type_raw"):
        key = state["vessel_type_raw"].strip().lower()
        state["propulsion_category"] = GEAR_TO_PROPULSION.get(key)
    return state
```

**Daily slot computation (new — needed for multi-day trips):** Track 3's Risk Engine expects one Gates-1–5 run **per day** of the trip, aggregated worst-case — not one snapshot for the whole `time_window`. The Planner (or a small helper right after it) expands `time_window` + `trip_duration_hours` into `daily_slots`:

```python
def compute_daily_slots(time_window: dict, trip_duration_hours: int) -> list[str]:
    start = parse_date(time_window["start"])
    num_days = max(1, ceil(trip_duration_hours / 24))
    return [(start + timedelta(days=i)).date().isoformat() for i in range(num_days)]
```

`daily_slots` then drives how many times each data agent gets called (Section 6) and how many entries `aggregated_conditions` ends up with (Section 7).

**Intent confidence gating (new — closes a real single point of failure):** everything downstream — which agents get called, which pipelines run, whether the query bypasses Track 3 entirely — depends on `intent` being correct. Right now nothing checks how sure the Planner actually was before that intent drives routing. Fix: the Planner's structured-extraction schema also returns `intent_confidence` (0.0–1.0), and `missing_fields` is only computed once that confidence clears a threshold — a low-confidence intent shouldn't even get to the slot-filling check, it needs disambiguation first.

```python
INTENT_THRESHOLD = 0.7   # starting point — tune against a labeled set of ambiguous
                          # test queries once the team has one; LLM self-reported
                          # confidence is not reliably calibrated out of the box

def planner_node(state: MarineQueryState) -> MarineQueryState:
    extracted = call_llm_structured(
        prompt=PLANNER_PROMPT,
        input_text=state["translated_query"],   # English, from the Multilingual Layer —
                                                  # NEVER state["raw_query"] here
        schema=PlannerExtractionSchema,   # now includes intent_confidence
    )
    state.update(extracted)
    state = normalize_propulsion(state)
    if state.get("time_window"):
        state["daily_slots"] = compute_daily_slots(
            state["time_window"], state.get("trip_duration_hours", 24)
        )
    # only check slots once the intent itself is trusted
    if state["intent_confidence"] >= INTENT_THRESHOLD:
        state["missing_fields"] = compute_missing_fields(state)
    else:
        state["missing_fields"] = []
    return state

def needs_clarification(state: MarineQueryState) -> str:
    if state.get("intent_confidence", 0) < INTENT_THRESHOLD:
        state["clarification_reason"] = "intent"
        return "clarify_intent"
    if state.get("missing_fields"):
        state["clarification_reason"] = "fields"
        return "clarify_fields"
    return "proceed"
```

---

## 5. Clarification Node

**Job:** two distinct jobs, not one — and this is the piece that changed most from the original design:

1. **Intent clarification** — the Planner wasn't confident about *what* the user wants at all (e.g. "is it okay to go fishing tomorrow?" could be `safety_check` or `conditions_lookup`). Ask a disambiguating question, then re-run the full Planner on the combined context.
2. **Missing-field clarification** — the intent is trusted, but a required slot for *that* intent is empty. Ask for just that field.

Both route through the same node (`clarification_reason` tells it which question to generate), and both loop back to the Planner:

```python
REQUIRED_FIELDS = {
    "safety_check": ["location", "time_window"],
    "pfz_lookup": ["location"],
    "route_plan": ["location", "time_window", "propulsion_category"],
    "alert_check": ["location"],
    # ...
}

def compute_missing_fields(state) -> list[str]:
    required = REQUIRED_FIELDS.get(state["intent"], [])
    return [f for f in required if not state.get(f)]

def clarification_node(state: MarineQueryState) -> MarineQueryState:
    state["clarification_turns"] = state.get("clarification_turns", 0) + 1

    if state["clarification_turns"] > MAX_CLARIFICATION_TURNS:
        # cap hit — stop asking, proceed with best guess rather than loop forever
        if state["clarification_reason"] == "intent":
            state["intent_confidence"] = 1.0   # force-trust the original guess
        else:
            state["missing_fields"] = []       # proceed with whatever we have
        return state

    if state["clarification_reason"] == "intent":
        question = generate_intent_disambiguation_question(state)  # e.g. the
        # "would you like a safety check, or marine conditions?" example
    else:
        question = generate_missing_field_question(state["missing_fields"][0])

    send_to_user(question)
    return state
```

Two things worth being deliberate about, since they weren't obvious before this change:
- **`clarification_turns` is a single cap covering both reasons combined**, not one cap per reason — a query that's persistently ambiguous on intent could otherwise loop forever even with a per-reason cap of 3 each. `MAX_CLARIFICATION_TURNS` (e.g. 3) is the one number that bounds the whole clarification loop.
- **What happens when the cap is hit differs by reason**: for missing fields, falling back to defaults (last known location, "next 12 hours") is safe. For intent ambiguity, there's no safe default field to fall back to — the only reasonable move is to trust the Planner's original (low-confidence) guess and proceed anyway, rather than silently picking an intent at random.

---

## 6. Supervisor Agent

**Job:** the routing loop — and this is the actual core of "is this an AI chatbot that can really plan." It has **two separate decisions to make**, not one:

- Which of **Riddhi's data agents** (weather/marine/GIS) does this query need?
- Which of **Nandini's downstream pipelines** (Risk Engine, Productivity ML, Route Optimization) does this query need?

Both are intent-driven and both are decided once, right after clarification passes — before any tool is called. Skipping the second decision is the most likely place this architecture silently breaks: without it, every query — even "what is a PFZ?" — would run the full Risk + Productivity + Route stack, which is wasted computation and pollutes simple answers with irrelevant scores.

```python
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
    "conditions_lookup":  [],                          # raw data report, no scoring
    "alert_check":        ["risk"],
    "route_plan":         ["risk", "route_optimization"],
    "productivity_query": ["productivity"],
    "general":            [],                          # pure conversational, no pipeline
}

def supervisor_node(state: MarineQueryState) -> MarineQueryState:
    if not state.get("agents_required"):
        state["agents_required"] = INTENT_TO_AGENTS.get(state["intent"], [])
        state["pipelines_required"] = INTENT_TO_PIPELINES.get(state["intent"], [])
        # one (agent, day) pair per day in daily_slots — NOT one call per query.
        # GIS is location-based, not day-based, so it's only ever called once.
        days = state.get("daily_slots") or ["single"]  # "single" for queries with no date range
        state["agents_pending"] = [
            (agent, day)
            for agent in state["agents_required"]
            for day in (["single"] if agent == "gis" else days)
        ]
    return state
```

**Route to the next pending agent, or hand off with the pipeline flags attached:**

```python
def route_next_step(state: MarineQueryState) -> str:
    pending = state.get("agents_pending", [])
    if pending:
        next_agent, _ = pending[0]   # peek only — the tool node itself pops on completion
        return f"call_{next_agent}"
    if not state["pipelines_required"]:
        return "direct_response"   # e.g. "general" intent — skip Track 3 entirely
    return "aggregate"             # NEW — always flatten before handing off, see Section 7
```

`pipelines_required` travels with the state into Track 3, so Nandini's engines read it rather than each deciding independently whether they're relevant — e.g. the Decision Engine only runs Productivity scoring if `"productivity" in state["pipelines_required"]`. This is the single field that makes the two-pipeline architecture (Safety + Productivity) actually intent-aware instead of running both on every query.

**The `general` intent and `direct_response` path** matter for the "own AI chatbot" framing specifically — pure explainer questions ("what is a PFZ?", "how is risk calculated?") shouldn't touch Riddhi's or Nandini's code at all; they can be answered by an LLM node directly off the query, bypassing the whole pipeline. Without this branch, the system can only ever answer data-lookup questions, not general conversation — worth confirming with the team whether a lightweight direct-response node is in scope for the demo or explicitly out of scope.

This routing logic is the piece most worth demoing on its own — it's the clearest visual proof of real "agentic" behavior (autonomous, intent-driven tool *and* pipeline selection), so log every decision the supervisor makes for the demo narrative.

**One case flagged as out of scope for now:** "why has fish productivity declined in a region" (from the problem statement) implies comparing current data against historical trends — that's a different shape of query than a single pipeline run, and isn't covered by this intent table. Worth raising with the team as a known gap rather than quietly not handling it.

**Multi-day trips (fixed a real gap):** Track 3's spec runs Gates 1–5 once per day for multi-day trips, aggregated worst-case — a 3-day trip needs 3 separate data snapshots, not one. The `(agent, day)` pending-pairs structure above handles this: for a 3-day `route_plan` query, `agents_pending` ends up with 9 entries (weather×3, marine×3, gis×1), and the Supervisor loop naturally calls each agent once per day. Riddhi's tool functions stay simple, single-day, deterministic functions (`fetch_weather(lat, lng, day)`) rather than needing to be multi-day-aware themselves — that complexity stays entirely in the Supervisor's loop, not in Track 2's code.

---

## 7. Data Aggregation Node — now owned by you

**The gap this closes:** Track 3's Risk Engine spec expects a **flat** input per day — `wind_kmph`, `wave_height_m`, `distance_from_shore_km` directly on one object. What the Supervisor loop produces is **nested by agent, then by day** (`tool_results["weather"]["2026-08-31"]`). Nothing turns one shape into the other unless a node explicitly does it — this is the "Data Aggregation" step from the original architecture diagram. It was previously an open question whose job this was; it's now yours, which simplifies the integration story since one person owns everything from raw query to the flat state Nandini reads.

**It's a pure reshape function** — no LLM calls, no business logic (no risk thresholds, no scoring). That's worth keeping true even now that you own it: resist the temptation to sneak any risk/scoring logic in here just because it's convenient — Gates 1–5 stay entirely Nandini's.


```python
def aggregation_node(state: MarineQueryState) -> MarineQueryState:
    days = state.get("daily_slots") or ["single"]
    aggregated = {}
    for day in days:
        aggregated[day] = {
            "wind_kmph": state["tool_results"].get("weather", {}).get(day, {}).get("wind_kmh"),
            "wave_height_m": state["tool_results"].get("marine", {}).get(day, {}).get("wave_m"),
            "distance_from_shore_km": state["tool_results"].get("gis", {}).get("single", {}).get("distance_from_shore_km"),
            "chlorophyll": state["tool_results"].get("marine", {}).get(day, {}).get("chlorophyll"),
            "sst": state["tool_results"].get("marine", {}).get(day, {}).get("sst"),
            # extend field-by-field against Track 3's Section 2 spec — this list should be
            # reviewed with Nandini directly since she knows exactly what Gates 1-5 read
        }
    state["aggregated_conditions"] = aggregated
    state["ready_for_risk_engine"] = True
    return state
```

Sits in the graph as its own node (Section 2's skeleton already reflects this): `supervisor → aggregation → risk_engine`. Keeping it as a separate node rather than folding it into the top of `risk_engine_node` means it's independently testable and doesn't quietly become "half Track 1's problem, half Track 3's problem" inside someone else's function.

---

## 8. Integration contracts (write these down, literally, in a shared doc)

| Handoff | What you give them | What you expect back |
|---|---|---|
| → Riddhi (Weather/Marine tools) | `lat`, `lng`, `day` (single day, plain args — not the whole state) | a dict written into `state["tool_results"][<agent_name>][<day>]` |
| → Riddhi (GIS tool) | `lat`, `lng` (called once, not per day) | a dict written into `state["tool_results"]["gis"]["single"]`, including `distance_from_shore_km` |
| → Nandini (Risk Engine) | full `MarineQueryState` where `ready_for_risk_engine == True` and `aggregated_conditions` is populated and flat | not your concern past this point |
| → Nandini (Explanation Agent) | the `translate_response(text, target_lang)` function from Section 3 | translated text in the user's original language |

Keep tool function signatures plain (`fetch_weather(lat, lng, day)`), not `fetch_weather(state)` — it keeps Riddhi's code testable independently of your graph. Note the signature changed from a `time_window` range to a single `day` — this is a direct consequence of the multi-day fix in Section 6, worth flagging to Riddhi since it affects her function signatures too.

---

## 9. Testing strategy

- **Unit-test each node** with hand-built `MarineQueryState` dicts — don't wait for a real LLM or real APIs to test routing logic.
- **Fixture-mock Track 2's tools** with realistic fake JSON (wind speed, wave height, chlorophyll ranges) so you can run the full graph before Riddhi's tools exist.
- **Test the aggregation node separately** with hand-built nested `tool_results` fixtures — since it's a pure reshape function, it's the easiest node in the whole graph to get full test coverage on, and bugs here silently corrupt everything Track 3 sees.
- **Test the translation layer against Bhashini's actual outage/timeout behavior early** — mock a failed Bhashini call specifically to confirm the Google Translate fallback actually fires, rather than discovering it doesn't work during the live demo.
- **End-to-end trace test:** run 4–5 canned queries covering each intent through the full stub graph and eyeball the final state — this becomes your integration demo before real data is plugged in. Include at least one non-English query in this set now that you own the multilingual path end-to-end.

---

## 10. Build order (within Track 1, in order)

1. Draft the state schema → circulate to Riddhi & Nandini for sign-off (do this today, not after building)
2. Build the LangGraph skeleton with everything stubbed, including the language and aggregation nodes → confirm it runs end-to-end
3. Implement the Multilingual Layer (Section 3) — start with `langdetect` + Google Translate only, add Bhashini once you've evaluated its API access/latency; it's a straightforward swap since `translate_text` is already isolated behind one function
4. Implement Planner Agent (start with hardcoded parsing to unblock the graph, swap in real LLM call after), including propulsion normalization and daily_slots computation
5. Implement Clarification Node + retry cap
6. Implement Supervisor's intent→agents/pipelines mapping and per-day routing loop
7. Implement the Data Aggregation node against Track 3's actual field list (get this reviewed by Nandini specifically)
8. Swap stub tool nodes for Riddhi's real functions as they land
9. Add logging around every supervisor decision (useful for both debugging and the demo narrative)

---

## 11. Decisions to lock with the team this week

- Final field names in `MarineQueryState` (change nothing after Riddhi/Nandini start coding against it)
- The intent → required-agents/pipelines mapping tables (Section 6) — this determines which of Riddhi's tools *and* which of Nandini's engines actually run per query type
- Max clarification turns and fallback behavior when the cap is hit
- **The exact field list inside `aggregated_conditions`** — must be reviewed against Track 3's Section 2 spec line-by-line with Nandini, not assumed from the example above
- **The `GEAR_TO_PROPULSION` mapping table** (Section 4) — needs real gear names from the team's target region (Kerala coast), not the placeholder set shown here
- **`INTENT_THRESHOLD` and `MAX_CLARIFICATION_TURNS`** (Sections 4–5) — starting values of `0.7` and `3` are guesses; tune both against a small labeled set of deliberately ambiguous test queries before the demo, not on gut feel
- **The intent-disambiguation question wording** for each pair of commonly-confused intents (e.g. `safety_check` vs `conditions_lookup`) — worth drafting these explicitly rather than leaving it fully to the LLM, so the phrasing stays consistent and short enough for SMS/voice channels later
- **Bhashini API access** — confirm registration/API-key process early (Section 3); it's a government API and onboarding lead time is an unknown until you've actually tried it, so don't leave this until late in the build
- **Which Indian languages to actually test against** for the demo — pick 2–3 (e.g. Malayalam, Hindi, Tamil) rather than claiming broad regional support untested; judges may ask you to demo a specific one live
