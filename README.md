# ORCA - Marine Intelligence Platform

ORCA is an agentic AI marine intelligence platform designed to process multi-channel user queries (in any language) and structure them into robust state representations, evaluate weather and marine conditions, and provide route optimizations and safety evaluations for marine vessels.

## Project Structure

```
├── .env.example       # Example environment variables
├── .gitignore         # Ignore generated files and directories
├── pyproject.toml     # Dependencies and project metadata
├── README.md          # Project documentation (this file)
├── src/
│   └── orca/
│       ├── __init__.py
│       ├── graph.py   # LangGraph orchestration skeleton and logic
│       └── state.py   # MarineQueryState defining the shared state schema
└── tests/
    ├── __init__.py
    └── test_graph.py  # End-to-end tests for the graph
```

## Collaborator Guidelines

This repo is structured for seamless collaboration across three tracks.

**Track 1: Orchestration (Navya)**
- **Role:** Handles language parsing, intent extraction, state management, and orchestration routing.
- **Where to code:** `src/orca/state.py` (for State definitions) and the core `src/orca/graph.py` structure.

**Track 2: Data Agents (Riddhi - Weather/Marine/GIS)**
- **Role:** Implements the tool nodes that retrieve data based on the normalized queries.
- **Where to code:** Please create a module at `src/orca/data_agents.py` (or similar) to house your logic. 
- **Graph Integration:** Update the `weather_tool_node`, `marine_tool_node`, and `gis_tool_node` stubs in `src/orca/graph.py` to call your real functions. Your functions should expect single plain arguments like `lat`, `lng`, and `day`, and return dictionaries to be integrated into `state["tool_results"]`.

**Track 3: Decision Engine (Nandini - Risk Engine, Productivity, Route Optimization, Explanation Agent)**
- **Role:** Evaluates the aggregated data to make safety and risk decisions.
- **Where to code:** Please create a module at `src/orca/decision_engine.py` (or similar).
- **Graph Integration:** Update the `risk_engine_node` in `src/orca/graph.py` to call your models. You can rely on the data structured inside `aggregated_conditions` and ensure `ready_for_risk_engine` is `True`.
