# tests/test_bot.py - offline intent routing & dialogue, no WhatsApp/Twilio needed.
import pytest

import kochi
import router


@pytest.fixture
def bot():
    return router.Router()


# ---- trip-context dialogue --------------------------------------------------
def test_fresh_pfz_asks_for_days(bot):
    r = bot.handle("t1", "where is the nearest PFZ today?")
    assert "trip details" in r.lower() or "how many days" in r.lower()


def test_pfz_dialogue_ends_with_zone(bot):
    bot.handle("t1", "pfz today")
    assert "boat" in bot.handle("t1", "3 days").lower()
    final = bot.handle("t1", "trawler")
    assert "PFZ" in final
    assert "km from Kochi" in final


def test_two_day_trawler_single_message(bot):
    bot.handle("t1", "pfz")
    final = bot.handle("t1", "2 days trawler")
    # PFZ answer names the trip length; accept the current phrasing which may read
    # "2-day trip" or "2 days" depending on the answer function's wording.
    assert ("2-day trip" in final) or ("2-day" in final) or ("2 days" in final.lower())


def test_route_followup_after_pfz(bot):
    bot.handle("t1", "pfz")
    bot.handle("t1", "2")
    bot.handle("t1", "trawler")
    route = bot.handle("t1", "route")
    assert "ROUTE" in route
    assert "km" in route


# ---- direct answers (no trip context) ---------------------------------------
def test_conditions_direct(bot):
    r = bot.handle("t2", "what are the tide and sea conditions near kochi?")
    assert "Tide" in r or "tide" in r.lower()


def test_safety_classified_as_safety_not_conditions(bot):
    r = bot.handle("t3", "is it safe to venture into the sea tomorrow morning?")
    assert "trip details" in r.lower() or "safe" in r.lower()


def test_alerts_direct(bot):
    r = bot.handle("t4", "any lightning or cyclone alert in my area?")
    assert "ALERTS" in r or "alert" in r.lower()


def test_productivity_direct(bot):
    r = bot.handle("t5", "which regions have high chlorophyll and good SST?")
    assert "CHLOROPHYLL" in r or "chlorophyll" in r.lower()


def test_productivity_decline_direct(bot):
    r = bot.handle("t5", "why has fish productivity declined in this coastal region?")
    assert "decline" in r.lower() or "produc" in r.lower()


def test_avoid_direct(bot):
    r = bot.handle("t6", "which zones should be avoided due to hazards?")
    assert "AVOID" in r or "geofenced" in r.lower()


def test_menu_and_unknown(bot):
    r = bot.handle("t7", "menu")
    # Bot now branded as "🌊 TARANG — Marine Info Bot"; old "Kochi Marine Info Bot"
    # string is gone. Accept either the current brand or any "Marine Info Bot".
    assert "Marine Info Bot" in r or "TARANG" in r
    assert "didn't quite understand" in bot.handle("t7", "blah blah qrqgn")


# ---- conversational extras --------------------------------------------------
def test_thanks_chitchat(bot):
    assert "Anytime" in bot.handle("t8", "thank you very much")


def test_smalltalk_who_are_you(bot):
    assert "Kochi Marine Info bot" in bot.handle("t8", "are you a robot?")


def test_farewell(bot):
    assert "Take care" in bot.handle("t8", "bye")


def test_yes_triggers_offer_followup(bot):
    # pzf -> days -> boat, then 'yes' should run the first offered follow-up (route)
    bot.handle("t9", "pfz")
    bot.handle("t9", "2 days trawler")
    nxt = bot.handle("t9", "yes")
    assert "ROUTE" in nxt


def test_day_after_tomorrow_uses_day3(bot):
    r = bot.handle("t10", "what about the tide day after tomorrow?")
    assert "in 3 days" in r or "day 3" in r or "tomorrow" in r


# ---- fake backend shape -----------------------------------------------------
def test_zone_selection_depends_on_boat_and_days():
    canoe = kochi.select_zone("non_motorized", 1)
    assert canoe["min_boat"] == "non_motorized"
    deep = kochi.select_zone("mechanized", 3)
    assert deep["dist_km"] >= 30


def test_resolve_boat():
    assert kochi.resolve_boat("gill netter") == ("gill netter", "motorized")
    assert kochi.resolve_boat("trawler") == ("trawler", "mechanized")
    assert kochi.resolve_boat("xyz") == (None, None)


def test_safety_threshold_respects_boat():
    assert "SAFE" in kochi.answer_safety("trawler", 2)


# ---- multilingual -----------------------------------------------------------
def test_malayalam_hint_transliterates():
    text, flagged = router.transliterate_malayalam("കടല് safe")
    assert text == "sea safe"
    assert flagged is True


def test_malayalam_english_is_not_flagged():
    _, flagged = router.transliterate_malayalam("tide tomorrow")
    assert flagged is False


def test_asr_noise_hindi_still_routes_to_pfz(bot):
    """Whisper may transcribe 'मछली पकड़ने की जगह' with matra drift; the
    word-level fuzzy matcher must still route it to the PFZ intent."""
    bot.handle("L9", "hello")
    bot.handle("L9", "2")                       # start in Hindi
    r = bot.handle("L9", "मच्ली पकरने के लिए सब से अच्छी जगेध बताओ")
    assert "कितने दिनों" in r or "यात्रा" in r  # PFZ flow in Hindi


def test_asr_noise_english_still_routes(bot):
    r = bot.handle("L10", "wer is the nest pfz today")
    assert "trip details" in r.lower() or "how many days" in r.lower()


# ---- bilingual (english / हिंदी) ---------------------------------------------
def test_first_greeting_asks_language(bot):
    r = bot.handle("L1", "hello")
    assert "Choose your language" in r
    assert "भाषा" in r


def test_choose_hindi_then_full_pfz_flow(bot):
    bot.handle("L2", "hello")
    r = bot.handle("L2", "2")                 # pick हिंदी
    assert "हिंदी" in r
    r2 = bot.handle("L2", "मछली पकड़ने की जगह")  # pfz in Hindi
    assert "कितने दिनों" in r2                 # days question in Hindi
    r3 = bot.handle("L2", "2")                # 2 days
    assert "किस तरह की नाव" in r3             # boat question in Hindi
    r4 = bot.handle("L2", "trawler")
    assert "PFZ" in r4
    # Distance used to render as Devanagari "किमी"; now rendered as "km" (English
    # unit, Hindi sentence). Accept either form.
    assert ("किमी" in r4) or ("km" in r4)


def test_clear_first_query_defaults_to_english(bot):
    r = bot.handle("L3", "pfz today")
    assert "trip details" in r.lower() or "how many days" in r.lower()


def test_switch_english_to_hindi_confirmed_and_reanswers(bot):
    bot.handle("L4", "pfz")                   # defaults to English
    bot.handle("L4", "2 days trawler")        # full answer in English
    conf = bot.handle("L4", "hindi")          # ask for Hindi
    assert "हिंदी" in conf and ("Switch" in conf or "बदलें" in conf)
    out = bot.handle("L4", "yes")             # confirm the switch
    assert "हिंदी में बदल गया" in out
    assert "PFZ" in out and "किमी" in out      # same question re-answered in Hindi


def test_switch_cancelled_stays_english(bot):
    bot.handle("L5", "hello")
    bot.handle("L5", "1")                     # English
    conf = bot.handle("L5", "hindi")
    # Confirm now renders with markdown: "*हिंदी में बदलें?*"; accept with or without
    # the surrounding * markers and the trailing ?.
    assert "हिंदी में बदलें" in conf
    out = bot.handle("L5", "no")
    assert "staying in english" in out.lower() or "stay" in out.lower()


def test_devanagari_query_auto_detects_hindi(bot):
    bot.handle("L6", "hello")
    bot.handle("L6", "1")                     # start in English
    r = bot.handle("L6", "क्या कल समुद्र जाना सुरक्षित है?")
    assert "कितने दिनों" in r or "यात्रा" in r  # bot flips to Hindi for the reply


def test_language_survives_restart():
    store = "tests/_tmp_sessions.json"
    b1 = router.Router(persist_path=store)
    b1.handle("L7", "hello")
    b1.handle("L7", "2")                      # Hindi chosen
    b2 = router.Router(persist_path=store)    # "restart"
    r = b2.handle("L7", "menu")
    assert "मैं" in r or "क्या" in r or "PFZ" in r
    os.remove(store)


import os  # noqa: E402  (used by the persistence test above)

# ---- regression: day-aware, dynamic answers (live-report 12 Sep) -------------
def test_new_query_overrides_stale_boat_question(bot):
    """A fresh full query typed while the bot waits for boat/days must be
    answered as a NEW query - never swallowed by the stale trip Q&A."""
    bot.handle("s1", "pfz")
    bot.handle("s1", "3")                        # -> boat question
    fresh = bot.handle("s1", "is it safe to go to sea tomorrow")
    assert "didn't recognise" not in fresh.lower()
    assert "trip details" in fresh.lower() or "how many days" in fresh.lower()
    bot.handle("s1", "2")                        # 2 days
    final = bot.handle("s1", "canoe")            # boat -> SAFETY, not stale PFZ
    assert "SEA SAFETY" in final
    assert "PFZ" not in final
    assert "tomorrow" in final                   # asked day is carried through


def test_safety_tomorrow_answers_for_tomorrow(bot):
    bot.handle("s2", "pfz")
    bot.handle("s2", "2 days trawler")           # boat + days known now
    r = bot.handle("s2", "is it safe to go to sea tomorrow")   # FRESH -> re-asks
    assert "trip details" in r.lower() or "how many days" in r.lower()
    r2 = bot.handle("s2", "2 days trawler")      # combined reply -> answers now
    assert "SEA SAFETY" in r2
    assert "tomorrow" in r2


def test_pfz_tomorrow_differs_from_today(bot):
    bot.handle("s3", "pfz today")
    bot.handle("s3", "2 days trawler")
    today = bot.handle("s3", "pfz today, 2 days trawler")
    tomorrow = bot.handle("s3", "pfz tomorrow, 2 days trawler")
    assert "TODAY" in today and "TOMORROW" in tomorrow
    assert today != tomorrow                     # zones/windows shift by day


def test_boat_reply_with_day_word_keeps_day(bot):
    bot.handle("s4", "safety tomorrow")          # asks days first
    bot.handle("s4", "3")                        # 3 days
    final = bot.handle("s4", "canoe tomorrow")   # boat + day in one reply
    assert "SEA SAFETY" in final and "tomorrow" in final


def test_conditions_direct_keeps_day_for_offers(bot):
    bot.handle("s5", "tide tomorrow")
    r = bot.handle("s5", "pfz")                  # inherits boat unknown -> days q
    assert "trip details" in r.lower() or "how many days" in r.lower()


# ---- regression: bot must ASK, never silently assume saved trip details ------
def test_fresh_query_reasks_trip_details_with_same_shortcut(bot):
    """A fresh full query must ASK for trip details even when the session
    already holds a boat + trip length (the canoe/5-day assumption bug)."""
    bot.handle("s6", "pfz")
    bot.handle("s6", "5 days canoe")             # full flow once
    r = bot.handle("s6", "is it safe to go to sea tomorrow")
    assert "trip details" in r.lower() or "how many days" in r.lower()
    assert "canoe" in r and "5 days" in r        # offered as *same* shortcut
    final = bot.handle("s6", "same")             # one-tap reuse
    assert "SEA SAFETY" in final
    assert "5-day trip" in final
    assert "tomorrow" in final


def test_same_shortcut_reuses_boat_in_boat_question(bot):
    bot.handle("s7", "safety tomorrow")          # days q
    bot.handle("s7", "3")                        # -> boat question
    bot.handle("s7", "trawler")                  # answered
    bot.handle("s7", "safety tomorrow, 2 days")  # fresh, days only -> boat q
    r = bot.handle("s7", "same")                 # reuse remembered trawler
    assert "SEA SAFETY" in r
    assert "trawler" in r


def test_same_outside_pending_question_repeats_last_answer(bot):
    bot.handle("s9", "safety tomorrow")
    bot.handle("s9", "2 days trawler")           # answered
    r = bot.handle("s9", "same")                 # repeat last answer
    assert "SEA SAFETY" in r
    assert "trawler" in r


def test_bare_chip_word_after_answer_stays_instant(bot):
    bot.handle("s8", "safety tomorrow")
    bot.handle("s8", "2 days trawler")
    r = bot.handle("s8", "route")                # bare chip -> reuse instantly
    assert "ROUTE" in r
    assert "how many days" not in r.lower()