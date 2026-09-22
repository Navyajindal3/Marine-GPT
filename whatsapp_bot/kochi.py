"""
Kochi Fake Backend — Kochi Marine Info WhatsApp Bot.

This module IS the fake backend: no external APIs / keys, every value is
hardcoded realistic-looking data for Kochi Port so the bot demoes fully
offline. Swap these functions for real INCOIS/IMD/weather APIs later without
touching bot.py or router.py.
"""

from datetime import datetime, timedelta

# Kochi Port reference: Kochi Harbour mouth (approx.)
KOCHI_PORT = {"lat": 9.9686, "lng": 76.2361, "name": "Kochi Harbour"}

# Boat-type knowledge base -> propulsion category (mirrors the main ORCA repo)
SAFETY_LIMITS = {
    "non_motorized": {"wave_max": 0.8, "wind_max": 18, "label": "canoe/vallam (non-motorized)"},
    "motorized":     {"wave_max": 1.6, "wind_max": 32, "label": "outboard/gill-netter (motorized)"},
    "mechanized":    {"wave_max": 2.3, "wind_max": 42, "label": "trawler/purse-seiner (mechanized)"},
}

BOAT_TYPES = {
    "canoe": "non_motorized", "country boat": "non_motorized",
    "vallam": "non_motorized", "kattumaram": "non_motorized",
    "नाव": "non_motorized", "कैनो": "non_motorized", "वल्लम": "non_motorized",
    "कट्टुमरम": "non_motorized", "होडी": "non_motorized",
    "outboard": "motorized", "gill netter": "motorized", "ring netter": "motorized",
    "आउटबोर्ड": "motorized", "गिलनेटर": "motorized", "रिंग नेटर": "motorized",
    "trawler": "mechanized", "shrimp trawler": "mechanized",
    "purse seiner": "mechanized", "diesel trawler": "mechanized",
    "ट्रॉलर": "mechanized", "troller": "mechanized", "पर्स सीनर": "mechanized",
}

# Hindi display labels for boat types
BOAT_LABEL_HI = {
    "canoe": "कैनो (नौका)", "country boat": "देशी नाव", "vallam": "वल्लम",
    "kattumaram": "कट्टुमरम", "outboard": "आउटबोर्ड नाव", "gill netter": "गिलनेटर",
    "ring netter": "रिंग नेटर", "trawler": "ट्रॉलर", "shrimp trawler": "झींगा ट्रॉलर",
    "purse seiner": "पर्स सीनर", "diesel trawler": "डीज़ल ट्रॉलर",
}


def boat_label(label, lang="en"):
    """Display label for a resolved boat name in the requested language."""
    if lang == "hi":
        return BOAT_LABEL_HI.get(label, label)
    return label


BOAT_QUESTION = (
    "What boat type are you using?\n\n"
    "*Available options:*\n"
    "• Canoe\n"
    "• Vallam\n"
    "• Gill netter\n"
    "• Outboard\n"
    "• Trawler\n"
    "• Purse seiner\n\n"
    "Or reply *default* for a coastal motorboat."
)

BOAT_QUESTION_HI = (
    "आप किस तरह की नाव इस्तेमाल करते हैं?\n\n"
    "*उपलब्ध विकल्प:*\n"
    "• Canoe\n"
    "• Vallam / नाव\n"
    "• Gill netter\n"
    "• Outboard\n"
    "• Trawler\n"
    "• पर्स सीनर\n\n"
    "या तटीय मोटरबोट के लिए *default* लिखें।"
)


def boat_question(lang="en"):
    return BOAT_QUESTION_HI if lang == "hi" else BOAT_QUESTION

# Day-forecast table. Index = calendar day (1 = today ... 7 = a week ahead, the
# realistic marine-forecast horizon). One entry per day so safety/pfz/route
# answers can be dynamic per departure day AND cover any trip length.
FORECASTS = {
    1: {"wave_m": 1.1, "wind_kmph": 14, "vis_km": 8, "current_kn": 0.9,
        "sea": "calm to slight", "note": "fine for all boat types"},
    2: {"wave_m": 1.8, "wind_kmph": 27, "vis_km": 4, "current_kn": 1.5,
        "sea": "moderate, rising", "note": "motorized & mechanized only; watch wind squalls"},
    3: {"wave_m": 0.9, "wind_kmph": 11, "vis_km": 9, "current_kn": 0.8,
        "sea": "calm", "note": "good conditions, fish dispersal expected"},
    4: {"wave_m": 1.5, "wind_kmph": 21, "vis_km": 6, "current_kn": 1.2,
        "sea": "slight", "note": "moderate swell; small craft caution"},
    5: {"wave_m": 2.6, "wind_kmph": 34, "vis_km": 3, "current_kn": 2.0,
        "sea": "rough", "note": "rough seas; small-craft advisory likely"},
    6: {"wave_m": 1.3, "wind_kmph": 16, "vis_km": 7, "current_kn": 1.0,
        "sea": "calm to slight", "note": "fine for all boat types"},
    7: {"wave_m": 2.2, "wind_kmph": 30, "vis_km": 4, "current_kn": 1.7,
        "sea": "moderate, rising", "note": "motorized & mechanized only; watch wind squalls"},
}

# Tidal table for tomorrow (fake but realistic for Kochi):
TIDES = [
    {"time": "04:20", "type": "HIGH", "height_m": 0.85},
    {"time": "10:35", "type": "LOW",  "height_m": 0.25},
    {"time": "16:40", "type": "HIGH", "height_m": 0.92},
    {"time": "22:55", "type": "LOW",  "height_m": 0.30},
]

# Potential Fishing Zones (PFZ) — chlorophyll & SST favourable bands off Kochi.
# distance_km is measured from Kochi Harbour mouth. Zones MOVE day to day, so a
# second table exists for tomorrow/day-after -> the bot answers dynamically
# according to the day the user asked about.
FISHING_ZONES = [
    {"id": "P1", "name": "Inshore off Chellanam", "lat": 9.8220, "lng": 76.1900,
     "dist_km": 9, "chl": 6.8, "sst": 29.4, "min_boat": "non_motorized",
     "hint": "coated & vallam; morning haul of sardines"},
    {"id": "P2", "name": "Shelf off Kochi (south)", "lat": 9.8800, "lng": 76.0600,
     "dist_km": 18, "chl": 4.5, "sst": 30.1, "min_boat": "motorized",
     "hint": "ring net / gill net; shoals of oil-sardine"},
    {"id": "P3", "name": "Deep shelf off Vypin", "lat": 9.9810, "lng": 75.9100,
     "dist_km": 30, "chl": 2.9, "sst": 30.8, "min_boat": "mechanized",
     "hint": "trawler; dusk operation"},
]

# Tomorrow / day-after PFZ outlook: the upwelling front shifts north-west, chl
# strengthens off Munambam and the deep shelf cools slightly.
FISHING_ZONES_TOM = [
    {"id": "P1", "name": "Off Munambam", "lat": 9.8650, "lng": 76.1200,
     "dist_km": 13, "chl": 5.9, "sst": 29.2, "min_boat": "non_motorized",
     "hint": "coated & vallam; dawn mackerel run"},
    {"id": "P2", "name": "Shelf off Kochi (south)", "lat": 9.8800, "lng": 76.0600,
     "dist_km": 18, "chl": 5.1, "sst": 30.0, "min_boat": "motorized",
     "hint": "ring net / gill net; sardine shoals push north"},
    {"id": "P3", "name": "Deep shelf off Vypin", "lat": 9.9810, "lng": 75.9100,
     "dist_km": 30, "chl": 3.4, "sst": 30.6, "min_boat": "mechanized",
     "hint": "trawler; night berths pay off"},
]

# Best fishing windows per calendar day (the tide cycle shifts ~30 min/day).
PFZ_WINDOWS = {
    1: ("05:30–09:30 (high-tide push)", "16:40–19:00"),
    2: ("06:10–10:00 (early ebb run)", "17:10–19:30"),
    3: ("05:50–09:40 (neap-tide drift)", "16:55–19:15"),
}


def zones_for_day(day=1):
    """PFZ table for the asked day: 1 = today, 2/3 = tomorrow / day-after."""
    return FISHING_ZONES if (day or 1) <= 1 else FISHING_ZONES_TOM

# Route legs (waypoints) from Kochi Harbour to each PFZ zone.
ROUTE_LEGS = {
    "P1": [
        ("Kochi Harbour Mouth", 0, "calm, <1m"),
        ("Chellanam channel bar", 4.5, "slight, 0.8m"),
        ("Zone P1 (9.82N 76.19E)", 8.5, "calm, <1m"),
    ],
    "P2": [
        ("Kochi Harbour Mouth", 0, "calm, 1.1m"),
        ("Bypass dredged lane", 6.0, "moderate, 1.4m"),
        ("Bar off Fort Kochi", 11.5, "moderate, 1.6m"),
        ("Zone P2 (9.88N 76.06E)", 15.0, "rising, 1.8m"),
    ],
    "P3": [
        ("Kochi Harbour Mouth", 0, "calm, 1.0m"),
        ("SLNC fairway", 10.0, "moderate, 1.7m"),
        ("500m depth line", 21.0, "moderate, 2.0m"),
        ("Zone P3 (9.98N 75.91E)", 30.0, "moderate, 2.1m"),
    ],
}
# ---------------------------------------------------------------------------
# Alert / hazard info (fake, but realistic for the SW-monsoon demo)
# ---------------------------------------------------------------------------
ALERTS = {
    "weather": "Moderate SW-wind alert (29-33 km/h) valid 14:00-20:00 across "
               "the 15 km offshore band; rain squalls near Chellanam.",
    "cyclone": "No cyclone warning. A low-pressure lies ~700 km SE off Kochi; "
               "keep watching IMD/DISACC bulletins.",
    "lightning": [
        "Band 15-25 km offshore off Kochi (9.7-10.0N) — likely 13:30-17:00",
        "Near Vypin & Ezhikkara jetties — likely 15:00-18:30",
    ],
    "small_craft": "Small-craft advisory active for the dawn window; canoes to "
                   "stay inside the 6 km band.",
}

GEO_FENCES = [
    {"name": "Kochi Vessel Traffic Lane (north-south fairway)",
     "coords": "9.94-9.98N, 76.22-76.27E", "rule": "transit only; keep 500 m from marked buoys"},
    {"name": "Cochin MPA (marine park) — Vypin-Chellanam islands",
     "coords": "9.80-9.90N, 76.15-76.26E", "rule": "no fishing inside reef-protected subzone"},
    {"name": "Gundu Light & old jetty zone",
     "coords": "9.955N, 76.25E", "rule": "dredging in progress; keep 800 m clear"},
]

# ---------------------------------------------------------------------------
# Productivity / chlorophyll / SST
# ---------------------------------------------------------------------------
CHL_HOTSPOTS = [
    {"area": "Chellanam south",     "chl": 7.2, "sst": 29.6, "favourable": True},
    {"area": "Vypin west (8-12 km)", "chl": 5.4, "sst": 30.2, "favourable": True},
    {"area": "Kochi shelf (deep)",   "chl": 2.2, "sst": 30.9, "favourable": False},
]

PRODUCTIVITY_DECLINES = {
    "": "Kochi-region productivity is ~12% below the 5-yr mean. Drivers this season: "
        "warm SST anomaly (+0.6°C) delaying shoal formation, a sharp rise in outer-shelf "
        "trawler hours, weaker SE upwelling in the last full-moon window. Recovery sign: "
        "fresh chl blooms off Chellanam.",
    "chellanam":  "Strong recent algal bloom but shoal dispersed — inshore catch down; SST anomaly.",
    "palluruthi": "Higher demersal traffic — kg/vessel and average fish length are down.",
}

DISTANCE_LABELS = {9: "inshore", 18: "near-shore", 30: "offshore"}

# Hindi label maps for forecast/sea words
SEA_HI = {
    "calm to slight": "हल्की लहरें", "calm": "शांत", "slight": "हल्की",
    "moderate, rising": "मध्यम, बढ़ रही", "moderate": "मध्यम", "rough": "ऊँची लहरें",
}
NOTE_HI = {
    "fine for all boat types": "सभी नावों के लिए ठीक",
    "motorized & mechanized only; watch wind squalls":
        "केवल मोटर/मैकेनाइज़्ड नावें; हवा के झोंकों से सावधान",
    "good conditions, fish dispersal expected":
        "अच्छी स्थिति; मछलियाँ बिखर सकती हैं",
}
TIDE_TYPE_HI = {"HIGH": "ऊँचा", "LOW": "नीचा"}


def _hi(table, key):
    """Hindi lookup with English fallback."""
    return table.get(key, key)


# TARANG brand header shown at the top of every reply (see mock-up).
TARANG_HEADER = "🌊 *TARANG*"


def _day_tag(day, lang="en"):
    """Small 'asked-for day' tag line, e.g. '📅 Day: TOMORROW (2026-09-13)'."""
    d = day or 1
    if lang == "hi":
        return f"📅 *दिन:* {friendly_day(d, 'hi')} ({date_str(d - 1)})"
    return f"📅 *Day:* {friendly_day(d).upper()} ({date_str(d - 1)})"


def friendly_day(day_num: int, lang: str = "en") -> str:
    if lang == "hi":
        if day_num <= 1:
            return "आज"
        if day_num == 2:
            return "कल"
        if day_num == 3:
            return "परसों"
        return f"{day_num} दिनों में"
    if day_num <= 1:
        return "today"
    if day_num == 2:
        return "tomorrow"
    if day_num == 3:
        return "day after tomorrow"
    return f"in {day_num} days"


def date_str(offset_days: int = 0) -> str:
    """Calendar date for offset 0 = today, 1 = tomorrow, ... -> '2026-09-13'."""
    return (datetime.now() + timedelta(days=max(0, int(offset_days or 0))
                                        )).strftime("%Y-%m-%d")

def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def tomorrow_str() -> str:
    return (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
# ---------------------------------------------------------------------------
#  QUERY FUNCTIONS — each returns a ready-to-send WhatsApp message string
# ---------------------------------------------------------------------------

def resolve_boat(boat_or_label):
    """Map (boat label, propulsion category). (None,None) if unknown."""
    if not boat_or_label:
        return None, None
    text = boat_or_label.strip().lower()
    if text in ("default", "auto", "any"):
        return "gill netter", "motorized"
    for key, cat in BOAT_TYPES.items():
        if key in text:
            return key, cat
    return None, None


def select_zone(category, trip_days, day=1):
    """Pick the fake PFZ for the user's boat + trip length + day.
    Longer trips push the fleet one band deeper; the zones themselves shift
    day to day (zones_for_day)."""
    pool = [z for z in zones_for_day(day)]
    if category == "non_motorized":
        pool = [z for z in pool if z["min_boat"] == "non_motorized"]
        idx = 0
    elif category == "motorized":
        pool = [z for z in pool if z["min_boat"] in ("non_motorized", "motorized")]
        idx = 1 if trip_days and trip_days >= 2 else 0
    else:
        idx = 2 if trip_days and trip_days >= 2 else 1
    idx = min(idx, len(pool) - 1)
    return pool[idx]


def format_zone(z):
    return (f"📍 *{z['name']}* (PFZ {z['id']})\n"
            f"  {z['lat']:.4f}N, {z['lng']:.4f}E — ~{z['dist_km']} km from Kochi Harbour\n"
            f"  chl {z['chl']} mg/m³ | SST {z['sst']}°C\n"
            f"  {z['hint']}")


def _pfz_headline(day=1, lang="en"):
    """Day-aware PFZ headline: TODAY / TOMORROW / DAY AFTER TOMORROW + date."""
    day = day or 1
    if lang == "hi":
        word = "आज" if day <= 1 else ("कल" if day == 2 else "परसों")
        return f"*{word} ({date_str(day - 1)}) की सबसे नज़दीकी PFZ (कोच्चि)*"
    word = "TODAY" if day <= 1 else ("TOMORROW" if day == 2 else
                                     "DAY AFTER TOMORROW")
    return f"*NEAREST PFZ {word} (Kochi) — {date_str(day - 1)}*"


def answer_pfz(boat_type, trip_days=1, lang="en", day=1):
    label, cat = resolve_boat(boat_type)
    zone = select_zone(cat, trip_days, day)
    w1, w2 = PFZ_WINDOWS.get(day or 1, PFZ_WINDOWS[1])
    if lang == "hi":
        return (
            f"{TARANG_HEADER}\n\n"
            f"{_day_tag(day, 'hi')}\n\n"
            f"हाँ — आपके {boat_label(label, 'hi')} ({trip_days} दिन की यात्रा) के लिए "
            f"सबसे अच्छी मछली पकड़ने की जगह है 📍 *{zone['name']}* "
            f"(PFZ {zone['id']}), कोच्चि हारबर से ~{zone['dist_km']} किमी।\n\n"
            f"🐟 क्लोरोफिल: {zone['chl']} mg/m³ | SST: {zone['sst']}°C\n"
            f"🎣 {zone['hint']}\n"
            f"🎯 मछली पकड़ने की संभावना: {fishing_potential(zone, 'hi')}\n"
            f"🛡 जोखिम आकलन: {risk_score(cat, day, 'hi')[1]}\n"
            f"⏰ सबसे अच्छा समय: {w1} और {w2}\n\n"
            # "⚠️ डेमो डेटा — जाने से पहले INCOIS PFZ बुलेटिन ज़रूर देखें।\n"
            "रास्ते के लिए *\"route\"* लिखें।"
        )
    return (
        f"{TARANG_HEADER}\n\n"
        f"{_day_tag(day, 'en')}\n\n"
        f"Yes — the best fishing zone for your {label} ({trip_days}-day trip) is "
        f"📍 *{zone['name']}* (PFZ {zone['id']}), "
        f"~{zone['dist_km']} km from Kochi Harbour.\n\n"
        f"🐟 Chlorophyll: {zone['chl']} mg/m³ | SST: {zone['sst']}°C\n"
        f"🎣 {zone['hint']}\n"
        f"🎯 Fishing potential: {fishing_potential(zone, 'en')}\n"
        f"🛡 Risk assessment: {risk_score(cat, day, 'en')[1]}\n"
        f"⏰ Best window: {w1} and {w2}\n\n"
        # "⚠️ Demo data — cross-check INCOIS PFZ bulletin before sailing.\n"
        "*Type \"route\"* for the waypoints to this zone."
    )


def answer_conditions(day_num=1, lang="en"):
    f = FORECASTS.get(day_num, FORECASTS[1])
    if lang == "hi":
        tides = "\n".join(
            f"• {t['time']} {_hi(TIDE_TYPE_HI, t['type'])} पानी {t['height_m']}m"
            for t in TIDES)
        return (
            f"{TARANG_HEADER}\n\n"
            f"{_day_tag(day_num, 'hi')}\n\n"
            f"कोच्चि के पास {friendly_day(day_num, 'hi')} समुद्र: "
            f"{_hi(SEA_HI, f['sea'])}।\n\n"
            f"🌊 *ज्वार, समुद्र और मौसम — {friendly_day(day_num, 'hi')} "
            f"({date_str(day_num - 1)})*\n\n"
            f"🌊 समुद्र: {_hi(SEA_HI, f['sea'])}\n"
            f"💨 लहर: {f['wave_m']} मी | हवा: {f['wind_kmph']} किमी/घंटा\n"
            f"👁 दृश्यता: {f['vis_km']} किमी | 🌀 धारा: {f['current_kn']} kn\n"
            f"ℹ️ नोट: {_hi(NOTE_HI, f['note'])}\n\n"
            f"🌊 *ज्वार-भाटा — {friendly_day(day_num, 'hi')}*\n{tides}\n\n"
            "💡 ऊँचे पानी के बाद 1 घंटे के भीतर रवाना होना सबसे सुरक्षित।"
        )
    tides = "\n".join(f"• {t['time']} {t['type']} {t['height_m']} m" for t in TIDES)
    return (
        f"{TARANG_HEADER}\n\n"
        f"{_day_tag(day_num, 'en')}\n\n"
        f"Sea near Kochi {friendly_day(day_num, lang)}: {f['sea']}.\n\n"
        f"🌊 *Tide, Sea & Weather — {friendly_day(day_num, lang)} "
        f"({date_str(day_num - 1)})*\n\n"
        f"🌊 Sea: {f['sea']}\n"
        f"💨 Wave: {f['wave_m']} m | Wind: {f['wind_kmph']} km/h\n"
        f"👁 Visibility: {f['vis_km']} km | 🌀 Current: {f['current_kn']} kn\n"
        f"ℹ️ Note: {f['note']}\n\n"
        f"🌊 *Tides — {friendly_day(day_num, lang)}*\n{tides}\n\n"
        "💡 Safer to depart within 1 h of slack water after high tide."
    )


def risk_score(boat_cat, day=1, lang="en"):
    """'28/100 - Low' style risk chip, coherent with the web-app score card."""
    day = min(max(int(day or 1), 1), max(FORECASTS))
    f = FORECASTS[day]
    lim = SAFETY_LIMITS.get(boat_cat, SAFETY_LIMITS["motorized"])
    wave_r = f["wave_m"] / lim["wave_max"]
    wind_r = f["wind_kmph"] / lim["wind_max"]
    score = int(min(99, max(8, (0.6 * wave_r + 0.4 * wind_r) * 55 + 8)))
    verdict = "Low" if score < 35 else ("Medium" if score < 60 else "High")
    if lang == "hi":
        v = {"Low": "कम", "Medium": "मध्यम", "High": "अधिक"}[verdict]
        return score, f"{score}/100 - {v}"
    return score, f"{score}/100 - {verdict}"


def fishing_potential(zone, lang="en"):
    """'High/Medium/Low' catch-potential chip from chlorophyll, web-app style."""
    chl = float(zone.get("chl") or 0)
    level = "High" if chl >= 5.0 else ("Medium" if chl >= 3.5 else "Low")
    if lang == "hi":
        return {"High": "उच्च", "Medium": "मध्यम", "Low": "कम"}.get(level, level)
    return level


def answer_safety(boat_type, trip_days=1, lang="en", day=1):
    label, cat = resolve_boat(boat_type)
    lim = SAFETY_LIMITS[cat]
    days = max(1, int(trip_days or 1))
    day = max(1, int(day or 1))
    hi = lang == "hi"
    depart = friendly_day(day, lang)
    # Trip day n maps onto calendar day (day + n - 1). Show EVERY day of the
    # trip (a full week is the forecast horizon; longer trips get a note).
    n_days = min(days, max(FORECASTS))
    mapped = [min(day + n - 1, max(FORECASTS)) for n in range(1, n_days + 1)]
    ok_days = [FORECASTS.get(fi, FORECASTS[1])["wave_m"] <= lim["wave_max"]
               and FORECASTS.get(fi, FORECASTS[1])["wind_kmph"] <= lim["wind_max"]
               for fi in mapped]
    safe = all(ok_days)
    lines = [TARANG_HEADER, ""]
    # Direct conversational verdict first (mock-up style: "Yes, it is safe ...")
    if hi:
        lines.append(f"{'हाँ, ' if safe else 'नहीं — '}"
                     f"{depart} कोच्चि के पास आपकी {boat_label(label, 'hi')} के लिए "
                     f"{'समुद्र में जाना सुरक्षित है।' if safe else 'समुद्र में जाना ठीक नहीं है।'}")
        lines.append("")
        lines.append(f"🛡 *समुद्र सुरक्षा — {boat_label(label, 'hi')}, {days} दिन की यात्रा — "
                     f"रवानगी: {depart} ({date_str(day - 1)})*")
    else:
        lines.append(f"{'Yes, ' if safe else 'No — '}it is "
                     f"{'safe' if safe else 'NOT safe'} to go fishing {depart} "
                     f"near Kochi on your {label}.")
        lines.append("")
        lines.append(f"🛡 *SEA SAFETY — {label}, {days}-day trip — departing "
                     f"{depart} ({date_str(day - 1)})*")
    # Trip day n maps onto calendar day (day + n - 1); ok_days/safe computed above.
    for n, (fi, ok) in enumerate(zip(mapped, ok_days), start=1):
        f = FORECASTS.get(fi, FORECASTS[1])
        dstr = date_str(fi - 1)
        mark = "🟢" if ok else "🔴"
        if hi:
            lines.append(f"{mark} दिन {n} ({dstr}) ({_hi(SEA_HI, f['sea'])}): "
                         f"लहर {f['wave_m']}मी (सीमा {lim['wave_max']}मी), "
                         f"हवा {f['wind_kmph']} किमी/घंटा (सीमा {lim['wind_max']})")
        else:
            lines.append(f"{mark} Day {n} ({dstr}) — 🌊 sea: {f['sea']}, "
                         f"wave {f['wave_m']} m (limit {lim['wave_max']} m), "
                         f"💨 wind {f['wind_kmph']} km/h (limit {lim['wind_max']} km/h)")
    if days > n_days:  # beyond the week-ahead forecast horizon
        if hi:
            lines.append(f"📅 दिन {n_days + 1}–{days}: सप्ताह-भर का पूर्वानुमान — "
                         "यही पैटर्न जारी रहेगा।")
        else:
            lines.append(f"📅 Days {n_days + 1}–{days}: beyond the 7-day forecast — "
                         "expect the same weekly pattern.")
    lines.append("")
    if hi:
        lines.append("✅ *जाना सुरक्षित है।*\n" if safe
                     else "⚠️ *सावधान — इस नाव के लिए मौसम प्रतिकूल।*\n")
        if 2 in mapped and cat != "mechanized":
            lines.append(f"💡 लहरों का उछाल ({date_str(1)}, 1.8 मी) यात्रा में आता है — "
                         "छोटी यात्रा या मैकेनाइज़्ड नाव बेहतर।")
        score, chip = risk_score(cat, day, "hi")
        lines.append(f"🛡 *जोखिम आकलन:* {chip}")
    else:
        lines.append("✅ *SAFE to venture out.*\n" if safe
                     else "⚠️ *CAUTION — adverse window for this boat.*\n")
        if 2 in mapped and cat != "mechanized":
            lines.append(f"💡 The swell peak ({date_str(1)}, 1.8 m) falls inside this trip — "
                         "prefer a shorter trip or a mechanized boat.")
        score, chip = risk_score(cat, day, lang)
        lines.append(f"🛡 *Risk assessment:* {chip}")
    return "\n".join(lines)


ALERTS_HI = {
    "weather": "तेज़ हवाओं की चेतावनी: 14:00–20:00 तक तट से 15 किमी की पट्टी में "
               "29–33 किमी/घंटा हवाएँ; चेल्लनम के पास बारिश के झोंके।",
    "cyclone": "कोई चक्रवात चेतावनी नहीं। कोच्चि से ~700 किमी दक्षिण-पूर्व में "
               "लो-प्रेशर क्षेत्र; IMD/DISACC बुलेटिन देखते रहें।",
    "small_craft": "भोर के समय छोटी नावों के लिए चेतावनी जारी; कैनो 6 किमी की "
                   "पट्टी के भीतर रहें।",
}


def answer_alerts(lang="en"):
    light = "\n".join(f"{x}" for x in ALERTS["lightning"])
    if lang == "hi":
        return (
            f"{TARANG_HEADER}\n\n*कोच्चि के आसपास लाइव अलर्ट*\n\n"
            f"• {ALERTS_HI['weather']}\n"
            f"• {ALERTS_HI['cyclone']}\n"
            f"• {ALERTS_HI['small_craft']}\n\n"
            f"*बिजली गिरने के समय:*\n\n{light}\n\n"
            "कोच्चि तट के लिए अभी कोई चक्रवात चेतावनी लागू नहीं।"
        )
    return (
        f"{TARANG_HEADER}\n\n*LIVE ALERTS around Kochi*\n\n"
        f"• {ALERTS['weather']}\n"
        f"• {ALERTS['cyclone']}\n"
        f"• {ALERTS['small_craft']}\n\n"
        f"*Lightning windows:*\n\n{light}\n\n"
        "No cyclone watch in force for the Kochi coast."
    )


PRODUCTIVITY_DECLINES_HI = {
    "": "कोच्चि क्षेत्र की उत्पादकता पिछले 5 साल के औसत से ~12% कम है। इस मौसम के कारण: "
        "गर्म SST (+0.6°C) से मछलियों के झुंड बनने में देरी, बाहरी शेल्फ़ पर ट्रॉलर "
        "गतिविधि बढ़ना, और पिछली पूर्णिमा में कमज़ोर अपवेलिंग। राहत का संकेत: "
        "चेल्लनम के पास नए क्लोरोफिल ब्लूम।",
    "chellanam": "हालिया शैवाल वृद्धि के बावजूद झुंड बिखर गए — तटीय पकड़ घटी; SST असामान्य।",
    "palluruthi": "तली की मछलियों पर ज़्यादा मछली पकड़ — प्रति नाव किलो और औसत लंबाई घटी।",
}


def answer_productivity(region=None, lang="en"):
    if lang == "hi":
        spots = "\n".join(
            f"• {s['area']}: क्लोरोफिल {s['chl']} mg/m³, SST {s['sst']}°C --- "
            f"{'✅ अच्छा' if s['favourable'] else '❌ कम'}"
            for s in CHL_HOTSPOTS)
        decline = PRODUCTIVITY_DECLINES_HI.get((region or "").strip().lower(),
                                               PRODUCTIVITY_DECLINES_HI[""])
        return (f"{TARANG_HEADER}\n\n*क्लोरोफिल और SST हॉटस्पॉट (कोच्चि)*\n\n" + spots +
                "\n\n*पकड़ क्यों घटी?*📉\n" + decline)
    spots = "\n".join(
        f"• {s['area']}: chl {s['chl']} mg/m³, SST {s['sst']}°C --- {'✅ good' if s['favourable'] else '❌ low'}"
        for s in CHL_HOTSPOTS)
    decline = PRODUCTIVITY_DECLINES.get((region or "").strip().lower(), PRODUCTIVITY_DECLINES[""])
    return (f"{TARANG_HEADER}\n\n*CHLOROPHYLL & SST hot spots (Kochi)*\n\n" + spots +
            "\n\n*Why did productivity drop?*📉 \n" + decline)


GEO_RULE_HI = {
    "transit only; keep 500 m from marked buoys":
        "केवल गुज़रने के लिए; चिह्नित बुओं से 500 मीटर दूर रहें",
    "no fishing inside reef-protected subzone":
        "रीफ़-संरक्षित उप-क्षेत्र में मछली पकड़ना मना है",
    "dredging in progress; keep 800 m clear":
        "ड्रेज़िंग चल रही है; 800 मीटर दूर रहें",
}


def answer_avoid(lang="en"):
    if lang == "hi":
        zones = "\n".join(
            f"• *{z['name']}*\n   क्*षेत्र:* {z['coords']}\n   *नियम:* {_hi(GEO_RULE_HI, z['rule'])}"
            for z in GEO_FENCES)
        return (f"{TARANG_HEADER}\n\n*निषिद्ध / जियोफ़ेंस ज़ोन (कोच्चि)*\n\n" + zones +
                "\n\nहर बताए गए क्षेत्र से 500 मीटर की दूरी रखें।")
    zones = "\n".join(
        f"• *{z['name']}*\n   *coord:* {z['coords']}\n   *rule:* {z['rule']}"
        for z in GEO_FENCES)
    return (f"{TARANG_HEADER}\n\n*AVOID / GEOFENCED zones (Kochi)*\n\n" + zones +
            "\n\nKeep a 500 m buffer around every polygon listed above.")


def answer_route(boat_type, trip_days=1, lang="en", day=1):
    label, cat = resolve_boat(boat_type)
    zone = select_zone(cat, trip_days, day)
    legs = ROUTE_LEGS[zone["id"]]
    # Final waypoint must match the actually-selected zone (name/coords/dist),
    # since the PFZ tables shift day to day.
    legs = legs[:-1] + [(f"Zone {zone['id']} ({zone['lat']:.2f}N {zone['lng']:.2f}E)",
                         zone["dist_km"], "calm, <1m")]
    legs_text = "\n".join(f"▸ {i} km — {wp} ({sea})" for wp, i, sea in legs[1:])
    fuel = 0 if cat == "non_motorized" else round(zone["dist_km"] * (2.0 if cat == "motorized" else 6.5))
    eta = max(1, round(zone["dist_km"] / 18.0, 1))
    if lang == "hi":
        return (
            f"{TARANG_HEADER}\n\n"
            f"*रास्ता (ऑप्टिमाइज़्ड) — {zone['name']}*\n\n"
            f"रवानगी: {friendly_day(day, 'hi')} 05:30 ({date_str(day - 1)}) — कोच्चि हारबर → *{zone['dist_km']} किलोमीटर*\n"
            f"{legs_text}\n\n"
            f"⛽ *ईंधन अनुमान:* {fuel} लीटर (एक तरफ़ा) | समय ≈ {eta} घंटे (6 kn)।\n"
            "VTS लेन के पश्चिम में रहें; गुंडू लाइट के पास निषिद्ध क्षेत्र न पार करें।"
        )
    return (
        f"{TARANG_HEADER}\n\n"
        f"*ROUTE (optimised) to {zone['name']}*\n\n"
        f"Dep: {friendly_day(day, lang)} 05:30 ({date_str(day - 1)}) — Kochi Harbour → *{zone['dist_km']} km*\n"
        f"{legs_text}\n\n"
        f"⛽ Fuel est: {fuel} L one-way | ETA ≈ {eta} h at 6 kn.\n"
        f"Stay W of the VTS lane; no geofenced crossing near Gundu Light."
    )


def answer_menu(lang="en"):
    if lang == "hi":
        return (
            "🌊 *TARANG* — मरीन इंफो बोट (कोच्चि) 🐟\n\n"
            "मुझे कुछ भी पूछें:\n"
            "1. PFZ — 'आज सबसे नज़दीकी PFZ कहाँ है?'\n"
            "2. सुरक्षा — 'क्या कल सुबह समुद्र जाना सुरक्षित है?'\n"
            "3. स्थिति — 'कोच्चि के पास ज्वार/मौसम कैसा है?'\n"
            "4. अलर्ट — 'कोई बिजली/चक्रवात चेतावनी है?'\n"
            "5. उत्पादकता — 'क्लोरोफिल? SST? पकड़ क्यों कम हुई?'\n"
            "6. रास्ता — 'मेरे जहाज़ के लिए सबसे अच्छा रास्ता?'\n"
            "7. निषिद्ध क्षेत्र — 'कौन से इलाके में जाना मना है?'\n\n"
            "PFZ, सुरक्षा और रास्ते के लिए मैं पहले यात्रा के दिन + नाव पूछूँगा।\n\n"
            "🌐 भाषा बदलने के लिए 'english' लिखें।"
        )
    return (
        "🌊 *TARANG* — Marine Info Bot (Kochi) 🐟\n\n"
        "Send me any of:\n"
        "1. PFZ — 'where is the nearest PFZ today?'\n"
        "2. Safety — 'is it safe to go to sea tomorrow morning?'\n"
        "3. Conditions — 'what are the tide/weather near Kochi?'\n"
        "4. Alerts — 'any lightning or cyclone alert?'\n"
        "5. Productivity — 'chlorophyll? SST? why did catch drop?'\n"
        "6. Route — 'what is the best route for my vessel?'\n"
        "7. Avoid — 'which zones are forbidden/geofenced?'\n\n"
        "For PFZ, safety & route I'll first ask your trip days + boat type.\n\n"
        "🌐 Type 'हिंदी' to switch language."
    )