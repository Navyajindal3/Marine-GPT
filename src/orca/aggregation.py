from orca.state import MarineQueryState

def aggregation_node(state: MarineQueryState) -> MarineQueryState:
    tool_results = state.get("tool_results", {})
    weather_results = tool_results.get("weather", {})
    marine_results = tool_results.get("marine", {})
    gis_results = tool_results.get("gis", {})
    
    slots = state.get("daily_slots", [])
    if not slots:
        slots = ["single"]
        
    aggregated = {}
    
    for day in slots:
        day_weather = weather_results.get(day, {})
        day_marine = marine_results.get(day, {})
        day_gis = gis_results.get("single", {})
        
        # Adapter layer: Maps varying tool output names (Track 2) into the strict contract required by Track 3.
        # Current stub inputs: wind_kmh, wave_m (from weather), wave_m (from marine), distance_from_shore_km (from gis)
        # Expected outputs: wind_kmph, wave_height_m, distance_from_shore_km, chlorophyll, sst
        
        # Precedence: For wave_height_m, marine's reading wins over weather's because marine is the more direct source for sea-state data.
        day_agg = {
            "wind_kmph": day_weather.get("wind_kmh"),
            "wave_height_m": day_marine.get("wave_m") if day_marine.get("wave_m") is not None else day_weather.get("wave_m"),
            "distance_from_shore_km": day_gis.get("distance_from_shore_km"),
            "chlorophyll": day_marine.get("chlorophyll"),
            "sst": day_marine.get("sst")
        }
        aggregated[day] = day_agg
        
    state["aggregated_conditions"] = aggregated
    
    # Note: "ready_for_risk_engine" is a misnomer now that raw-conditions queries 
    # pass through here too, but we keep it since Track 3 is coding against it.
    state["ready_for_risk_engine"] = True
    
    return state
