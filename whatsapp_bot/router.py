"""
Router - conversational WhatsApp brain (pure if/else + state machine, no LLM).

Flow for ANY message:
  (1) normalize + transliterate Malayalam hints
  (2) greetings / farewell / chitchat / thanks / yes-no handling
  (3) weighted keyword intent classification (typo tolerance + priority tie-break)
  (4) optional trip Q&A (how many days -> what boat) for PFZ/safety/route
  (5) fake-backend answer + contextual follow-up offers so the chat keeps flowing

Sessions are per-phone and optionally persisted to a JSON file so chats survive
a bot restart.
"""
import json
import os
import re
import threading
from difflib import get_close_matches

import i18n
import kochi

# Language: a few Malayalam keyword hints (bot still answers in English)
MALAYALAM_HINTS = {
    "സുരക്ഷ": "safe", "കടല്": "sea", "വേലിയേറ്റം": "tide", "കാറ്റ്": "wind",
    "മത്സ്യം": "fish", "ഇടി": "lightning", "ചുഴലി": "cyclone",
    "മുന്നറിയിപ്പ്": "alert", "കാലാവസ്ഥ": "weather",
}
MALAYALAM_RANGE = range(0x0D00, 0x0D7F + 1)

# Romanized Hindi (Hinglish) -> Devanagari. Whisper often transcribes Hindi
# voice notes in LATIN letters ("kya kal samudra jana surakshit hai"); mapping
# those words to Devanagari makes the existing Hindi keyword tables + language
# detection work, so a spoken (or mistranscribed) Hinglish query is answered
# correctly and IN Hindi.
HINGLISH = {
    "kya": "क्या", "kal": "कल", "aaj": "आज", "parson": "परसों",
    "samudra": "समुद्र", "samundar": "समुद्र", "sagar": "समुद्र",
    "surakshit": "सुरक्षित", "suraksha": "सुरक्षा", "khatra": "खतरा",
    "khatarnak": "खतरनाक", "kshetra": "क्षेत्र",
    "machhli": "मछली", "machli": "मछली", "machhali": "मछली",
    "pakadne": "पकड़ने", "pakarna": "पकड़ना", "jagah": "जगह",
    "jage": "जगह", "kitaney": "कितने", "kitne": "कितने", "din": "दिन",
    "mausam": "मौसम", "jwar": "ज्वार", "bhata": "भाटा", "lahar": "लहर",
    "hawa": "हवा", "hawaa": "हवा",
    "chetawani": "चेतावनी", "chakravat": "चक्रवात", "toofan": "तूफान",
    "tufan": "तूफान", "bijli": "बिजली",
    "rasta": "रास्ता", "raasta": "रास्ता", "manahai": "मना है",
    "mana hai": "मना है", "bachkar": "बच कर",
    "utpadakta": "उत्पादकता", "klorofil": "क्लोरोफिल", "kam": "कम",
    "nauka": "नाव", "naav": "नाव", "madad": "मदद", "menyu": "मेन्यू",
    "namaste": "नमस्ते", "jana": "जाना", "jaana": "जाना",
}

_HINGLISH_RE = re.compile(
    r"\b(" + "|".join(sorted(HINGLISH, key=len, reverse=True)) + r")\b",
    re.IGNORECASE)


def hinglish_to_devanagari(text):
    """Romanized-Hindi -> Devanagari, when the text already isn't Indic."""
    if not text or any(ord(ch) in range(0x0900, 0x097F + 1) or
                       ord(ch) in MALAYALAM_RANGE for ch in text):
        return text
    return _HINGLISH_RE.sub(lambda m: HINGLISH[m.group(1).lower()], text)


def transliterate_malayalam(raw: str):
    """Swap known Malayalam words for English; report if Malayalam was seen."""
    has_ml = any(ord(ch) in MALAYALAM_RANGE for ch in raw)
    out = raw
    for ml, en in MALAYALAM_HINTS.items():
        if ml in out:
            out = out.replace(ml, en)
    return out, has_ml

# Intent keyword tables - multi-word phrases weigh double (2) vs single (1)
INTENT_KEYWORDS = {
    "menu": ["help", "menu", "start", "option", "what can you do", "show me",
             "मदद", "मेन्यू"],
    "alerts": ["alert", "warning", "lightning", "cyclone", "storm", "thunder",
               "squall", "rough sea", "bulletin", "danger warning",
               "चेतावनी", "बिजली", "चक्रवात", "तूफ़ान", "तूफान"],
    "productivity": ["productivity", "chlorophyll", "chl", "sst", "surface temp",
                     "why less fish", "why catch", "decline", "drop in catch",
                     "fish population", "upwelling", "less fish",
                     "उत्पादकता", "क्लोरोफिल", "पकड़ क्यों", "कम मछली"],
    "avoid": ["avoid", "restricted", "geofence", "geofenced", "prohibited",
              "forbidden", "hazardous", "hazard", "keep away", "marine park",
              "निषिद्ध", "मना है", "बच कर", "खतरनाक क्षेत्र"],
    "route": ["route", "course", "navigate", "waypoint", "vessel lane",
              "best path", "safest route", "heading", "safe way",
              "रास्ता", "रास्ते", "सुरक्षित रास्ता"],
    "conditions": ["tide", "tides", "weather", "sea condition", "wave", "wind",
                   "current", "visibility", "sea state", "forecast",
                   "tomorrow morning", "swell",
                   "ज्वार", "भाटा", "मौसम", "लहर", "हवा", "कल का मौसम"],
    "safety": ["safe", "venture", "go to sea", "go fishing", "should i go",
               "can i go", "risk", "dangerous", "go out",
               "सुरक्षित", "सुरक्षा", "खतरा", "जा सकता"],
    "pfz": ["pfz", "fishing zone", "fish zone", "fish today", "good fishing",
            "best fishing", "where fish", "where can i fish", "catch",
            "fish location", "spot", "good spot",
            "मछली पकड़ने", "मछली कहाँ", "पकड़ने की जगह", "मछली की जगह"],
    "call": ["phone call", "phone", "call me", "call", "calling", "ring",
             "connect on phone", "connect on a call", "voice call",
             "can we talk on phone", "can we talk on call",
             "can we call", "can we connect on call", "can we connect on phone", "callback", "гарячая линия", "phone pe baat",
             "phone par baat", "फोन", "फोन पर", "कॉल", "कॉल करें",
             "मेरा फोन नंबर", "telephonic", "telephonic conversation",
             "talk on phone", "talk on call", "speak over phone",
             "speaking", "baat kar lijiye", "baat karte hain"],
}

# tie-break order when two intents score equally (safety beats conditions, etc.)
PRIORITY = ["call", "safety", "pfz", "route", "conditions", "alerts",
            "productivity", "avoid", "menu"]

TRIP_CONTEXT_INTENTS = {"pfz", "safety", "route"}  # need days + boat first
KNOWN_RESET = ("cancel", "exit", "stop", "reset")
GREETINGS = {"hi", "hello", "hey", "hii", "hie", "namaste", "नमस्ते", "hola",
             "good morning", "good afternoon", "good evening"}

# contextual follow-up offers shown after each answer
OFFERS = {
    "pfz": ["route", "safety", "conditions"],
    "safety": ["route", "conditions", "alerts"],
    "route": ["safety", "conditions"],
    "conditions": ["alerts", "safety"],
    "alerts": ["conditions", "safety"],
    "productivity": ["pfz", "conditions"],
    "avoid": ["route", "safety"],
}

CHITCHAT = [
    (("thank you", "thanks", "thank", "thx", "dhanyavaad", "shukriya", "nanni"),
     "Anytime! That's what I'm here for 🐟"),
    (("are you a robot", "are you a bot", "are you real", "who are you",
      "what are you", "your name", "who made you", "about you"),
     "I'm 🌊 *TARANG* — the Kochi Marine Info bot 🐟.\n"
     "Type *menu* to see what I can do."),
    (("how are you", "how's it going", "how are things", "what's up",
      "sup", "how do you do"),
     "All calm here at Kochi harbour 🌊. What can I help with? \ne.g. *pfz* / *safety* / *tide* / *alerts*"),
    (("good morning", "good afternoon", "good evening"),
     "Good day! Ready to help with today's sea, tide & alerts."),
    (("i love you", "you are great", "awesome", "great bot", "nice bot", "good bot"),
     "Thank you! 😊 Happy fishing, and stay safe on the water! 🐟"),
]
# The conversational router ---------------------------------------------------
class Router:
    """Per-phone conversation state machine with optional JSON persistence."""

    def __init__(self, persist_path=None):
        self.persist_path = persist_path
        self._lock = threading.RLock()
        self.sessions = self._load() if persist_path else {}

    # persistence ----------------------------------------------------------
    def _load(self):
        if not self.persist_path or not os.path.exists(self.persist_path):
            return {}
        try:
            with open(self.persist_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save(self):
        if not self.persist_path:
            return
        with self._lock:
            tmp = self.persist_path + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(self.sessions, fh, ensure_ascii=False, indent=2)
                os.replace(tmp, self.persist_path)
            except OSError:
                pass

    def _prompt(self, number):
        with self._lock:
            return self.sessions.setdefault(number, self._default_session())

    @staticmethod
    def _default_session():
        return {
            "step": None, "intent": None, "trip_days": 1, "day": 1,
            "boat": None, "cat": "motorized", "offers": [], "last": None,
            "lang": None, "awaiting_lang": False, "pending_switch": None,
            "last_query": None, "map_kind": None,
        }

    def _reset(self, number, lang=None):
        """Wipe the dialogue state but KEEP the language preference."""
        with self._lock:
            old = self.sessions.pop(number, None) or {}
            keep = lang or old.get("lang")
            self.sessions[number] = self._default_session()
            self.sessions[number]["lang"] = keep
            self._save()
        return kochi.answer_menu(keep) if keep else i18n.ASK_LANG

    # normalisation & scoring -------------------------------------------------
    @staticmethod
    def _normalize(text):
        # \w misses Indic combining marks (matras/nukta) on Python 3.8, which
        # would shred Devanagari keywords - whitelist those script ranges too.
        return re.sub(r"[^\w\s\u0900-\u097F\u0D00-\u0D7F]", " ", text).lower()

    # keyword token index for fuzzy ASR matching (built once) ---------------
    _KW_TOKENS = None

    @classmethod
    def _kw_token_index(cls):
        if cls._KW_TOKENS is None:
            idx = []
            for intent, keys in INTENT_KEYWORDS.items():
                for k in keys:
                    for tok in k.split():
                        if len(tok) >= 3:
                            idx.append((tok, intent))
            cls._KW_TOKENS = idx
        return cls._KW_TOKENS

    @classmethod
    def _classify_scores(cls, text, fuzzy=True):
        scores = {}
        for intent, keys in INTENT_KEYWORDS.items():
            c = 0
            for k in keys:
                if k in text:
                    c += 2 if len(k.split()) > 1 else 1
            if c:
                scores[intent] = c
        if not fuzzy:  # strict mode: exact phrases only (language gate uses this)
            return scores
        # ASR/voice-note noise tolerance: word-level fuzzy match. Whisper on
        # Devanagari can drop/merge matras ('मछली' -> 'मच्ली'), so exact
        # phrase matching alone misses voice queries in Hindi.
        for tok in text.split():
            if len(tok) < 3:
                continue
            for kw, intent in cls._kw_token_index():
                if (abs(len(kw) - len(tok)) <= 3 and kw[0] == tok[0]
                        and get_close_matches(tok, [kw], n=1, cutoff=0.62)):
                    scores[intent] = scores.get(intent, 0) + 0.5
                    break
        return scores

    @classmethod
    def _classify(cls, text, fuzzy=True):
        scores = cls._classify_scores(text, fuzzy=fuzzy)
        if not scores:
            return None
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1],
                        PRIORITY.index(kv[0]) if kv[0] in PRIORITY else 99))
        return ranked[0][0]

    def _fuzzy_intent(self, text):
        """Tolerate small typos for short queries like 'pfze'/'tidew'."""
        if len(text.strip()) > 14:
            return None
        for intent, keys in INTENT_KEYWORDS.items():
            for k in keys:
                if len(k) >= 4 and get_close_matches(text, [k], n=1, cutoff=0.82):
                    return intent
        return None

    @staticmethod
    def _parse_days(text):
        nums = re.findall(r"\d+", text)
        return max(1, int(nums[0])) if nums else None

    @staticmethod
    def _day_offset(text):
        if "day after tomorrow" in text:
            return 3
        if "tomorrow" in text:
            return 2
        if "tonight" in text or "today" in text:
            return 1
        n = re.findall(r"\d+", text)
        return min(max(int(n[0]), 1), 3) if n else 1

    @staticmethod
    def _parse_day_offset(text):
        """Explicit day words ONLY -> 1 (today) / 2 (tomorrow) / 3 (day after).
        Bare digits are trip days, not calendar days, so '2 days trawler'
        never becomes 'tomorrow'. None = no day mentioned."""
        if "day after tomorrow" in text or "परसों" in text:
            return 3
        if "tomorrow" in text or "कल" in text or "നാളെ" in text:
            return 2
        if ("today" in text or "tonight" in text or "अभी" in text
                or "आज" in text or "ഇന്ന്" in text):
            return 1
        return None

    @staticmethod
    def _is_yes(text):
        return text in ("yes", "yep", "yeah", "ya", "sure", "ok", "okay",
                        "haan", "haan ji", "han", "ha", "हाँ", "हां", "जी",
                        "do it", "go ahead")

    @staticmethod
    def _is_no(text):
        return text in ("no", "nope", "nah", "not now", "nahi", "nahin",
                        "नहीं", "नही") or \
            ("no" in text and ("thanks" in text or "thank" in text))

    @staticmethod
    def _chitchat(text):
        for pats, reply in CHITCHAT:
            if any(p in text for p in pats):
                return reply
        return None
# main entry -------------------------------------------------------------
    def handle(self, number: str, raw: str) -> str:
        """One function for the whole WhatsApp conversation."""
        text, has_ml = transliterate_malayalam(raw.strip().lower())
        # romanized-Hindi voice transcripts -> Devanagari for keyword matching
        text = hinglish_to_devanagari(text)
        text = self._normalize(text)
        if not text or not text.strip():
            lang = self.sessions.get(number, {}).get("lang") or "en"
            return i18n.t(lang, "empty")
        reply = self._respond(number, text)
        if has_ml:
            reply = ("Note: Malayalam detected --- replying in English.\n\n" + reply)
        return reply

    def _respond(self, number, text):
        session = self._prompt(number)
        txt = text.strip()
        lang = session.get("lang")
        session["map_kind"] = None  # fresh message -> no stale map overlay

        # 0) language gate ----------------------------------------------------
        if not lang:
            choice = i18n.parse_lang_choice(txt)
            if choice:  # answered the bilingual ask -> set & show menu
                session["lang"] = choice
                session["asked_lang"] = True
                self._save()
                return i18n.t(choice, "lang_set") + "\n\n" + kochi.answer_menu(choice)
            if i18n.looks_hindi(text):  # Devanagari -> Hindi, no questions asked
                session["lang"] = "hi"
                self._save()
            elif session.get("asked_lang"):  # asked once already -> keep English
                session["lang"] = "en"
                self._save()
            else:
                # Fuzzy-tolerance on first contact too: a voice note or typed query
                # with a small typo (e.g. "can we connecvt on call") must still be
                # recognised as a clear intent, not sent to the bilingual language ask.
                intent0 = (self._classify(text, fuzzy=True)
                           or self._fuzzy_intent(text))
                small0 = (self._chitchat(text) or any(
                    w in text for w in ("bye", "goodbye", "good night")))
                if intent0 or small0:  # clear first query -> English, no friction
                    session["lang"] = "en"
                    self._save()
                else:  # greeting/unclear first contact -> bilingual ask (once)
                    session["asked_lang"] = True
                    self._save()
                    return i18n.ASK_LANG
        lang = session["lang"]

        # 0b) mid-chat Devanagari -> silently continue in Hindi (unless the
        # message is itself a language-switch request like "हिंदी")
        if lang != "hi" and i18n.looks_hindi(text) \
                and not i18n.detect_lang_request(text):
            lang = "hi"
            session["lang"] = "hi"
            self._save()

        # 1) explicit language-switch request ("hindi", "english", हिंदी, ...)
        lang_words = {"hindi", "english", "हिंदी", "अंग्रेज़ी", "अंग्रेजी",
                      "angrezi", "inglish", "in", "mein", "में", "lang",
                      "language", "please"}
        words = txt.split()
        switch_txt = txt in ("hindi", "english", "हिंदी", "अंग्रेज़ी",
                             "अंग्रेजी") or (
            len(words) <= 4 and all(w in lang_words for w in words))
        target = i18n.detect_lang_request(text) if switch_txt else None
        if target and target == lang:
            name = "हिंदी" if lang == "hi" else "English"
            return i18n.t(lang, "already_lang", langname=name)
        if target:
            session["pending_switch"] = target
            session["pending_text"] = text
            self._save()
            return i18n.confirm_switch(lang, target)

        # 2) yes/no answer to a pending language switch
        if session.get("pending_switch"):
            ptarget = session["pending_switch"]
            ptext = session.get("pending_text") or ""
            session["pending_switch"] = None
            session["pending_text"] = None
            if self._is_yes(txt):
                session["lang"] = ptarget
                self._save()
                reply = self._reanswer(number, session, ptext)
                return i18n.t(ptarget, "switched") + "\n\n" + reply
            if self._is_no(txt):
                self._save()
                return i18n.t(lang, "switch_cancel")
            self._save()  # not yes/no -> drop the switch, reply normally

        # 3) greetings / menu shortcuts
        if txt in GREETINGS or any(k in text for k in INTENT_KEYWORDS["menu"]):
            if any(w in text for w in KNOWN_RESET):
                return self._reset(number)
            return kochi.answer_menu(lang)

        # 4) farewell
        if any(w in text for w in ("bye", "goodbye", "good night",
                                   "अलविदा", "फिर मिलेंगे")):
            self._reset(number)
            return i18n.t(lang, "farewell")

        # 5) chitchat / thanks / small talk
        chat = self._chitchat(text)
        if chat:
            return chat

        # 6) yes / no for pending follow-up offers (keeps chat flowing)
        if self._is_yes(txt):
            if session["offers"]:
                nxt = session["offers"].pop(0)
                with self._lock:
                    self._save()
                return self._run_intent(number, session, nxt, text,
                                        followup=True)
            return i18n.t(lang, "yes_generic")
        if self._is_no(txt):
            session["offers"] = []
            with self._lock:
                self._save()
            return i18n.t(lang, "no_generic")

        # 7) mid-conversation steps (trip Q&A)
        if session["step"] == "ask_boat":
            return self._handle_boat_reply(number, session, text)
        if session["step"] == "ask_days":
            return self._handle_days_reply(number, session, text)

        if self._is_same(txt) and not session.get("step"):
            # 'same' typed while nothing is pending: repeat the last answer
            last = session.get("last")
            if not last:
                return i18n.t(lang, "unknown")
            if last in TRIP_CONTEXT_INTENTS:
                return self._final_answer(number, session, last, txt)
            return self._direct_answer(number, session, last,
                                       session.get("last_text") or txt)

        # 8) fresh query -> classify intent
        intent = self._classify(text) or self._fuzzy_intent(text)
        if not intent:
            return i18n.t(lang, "unknown")
        return self._run_intent(number, session, intent, text)

    def _boat_question_hint(self, session, lang):
        """Boat question + (when a boat is remembered) a 'same' shortcut."""
        q = kochi.boat_question(lang)
        if session.get("boat"):
            q += i18n.t(lang, "same_boat_hint",
                        boat=kochi.boat_label(session["boat"], lang))
        return q

    @staticmethod
    def _is_same(text):
        return text in ("same", "same as before", "as before", "wahi",
                        "pahle jaisa", "पहले जैसा", "पहले जैसा ही", "वही",
                        "वही नाव")

    def _run_intent(self, number, session, intent, text, followup=False):
        """Route the classified intent: trip Q&A first, else answer now.

        followup=True  -> came from the contextual offer chips (yes/route right
        after an answer): reuse the known boat/days instantly.
        A FRESH typed query ALWAYS (re)asks trip details first, offering the
        remembered values as a *same* shortcut - never silently assumed.
        (A bare one-word chip like 'route'/'safety' still counts as a
        follow-up, since that is what the offer line tells users to type.)"""
        lang = session.get("lang") or "en"
        if intent in TRIP_CONTEXT_INTENTS:
            # remember WHICH day the user asked about (today/tomorrow/...)
            d_off = self._parse_day_offset(text)
            if d_off:
                session["day"] = d_off
            # Single-word chips like 'pfz' / 'route' / 'safety' that the user type
            # after an answer are follow-ups (that's what the offer line tells them
            # to type). Also: a multi-word query that CARRIES AN EXPLICIT DAY WORD
            # AND we already know the boat is a fully-specified query -> answer now.
            # Never silently assume a boat though: no boat yet -> still ask for it.
            bare_chip = (len(text.split()) == 1 and text in
                         ("pfz", "safety", "route", "conditions", "alerts",
                          "productivity", "avoid"))
            has_day_word = self._parse_day_offset(text) is not None
            implicit_trip_days = self._parse_days(text)
            fully_specified = session["boat"] and (followup or bare_chip
                                                   or has_day_word)
            if fully_specified:
                d = implicit_trip_days
                if d:
                    session["trip_days"] = d
                    self._save()
                return self._final_answer(number, session, intent, text)

            # Otherwise we need trip details first. If the query already names
            # a boat or trip days, remember them and re-run so we only ask for
            # whichever is still missing (one question at a time).
            session["intent"] = intent
            session["last_text"] = text
            days = self._parse_days(text)
            boat, cat = kochi.resolve_boat(text)
            if days:
                session["trip_days"] = days
            if boat:
                session["boat"], session["cat"] = boat, cat
                session["step"] = None
                self._save()
                return self._final_answer(number, session, intent, text) + (
                    "\n\n" + i18n.t(lang, "ask_more"))
            session["step"] = "ask_days" if not days else "ask_boat"
            self._save()
            if not days:
                q = i18n.t(lang, "days_question")
                if session.get("trip_days"):
                    detail = f"{session['trip_days']} days"
                    if session.get("boat"):
                        detail += ", " + kochi.boat_label(session["boat"], lang)
                    q += i18n.t(lang, "same_days_hint", detail=detail)
                return q
            return self._boat_question_hint(session, lang)

        return self._direct_answer(number, session, intent, text)

    def _handle_days_reply(self, number, session, text):
        lang = session.get("lang") or "en"
        # 'same' -> reuse the remembered trip (and boat, when known) in one tap
        if self._is_same(text) and session.get("trip_days"):
            if session.get("boat"):
                session["step"] = None
                self._save()
                return self._final_answer(
                    number, session, session["intent"], text) + (
                    "\n\n" + i18n.t(lang, "ask_more"))
            session["step"] = "ask_boat"
            self._save()
            return self._boat_question_hint(session, lang)
        days = self._parse_days(text)
        if days is None:
            # Not a number -> the user may have asked a NEW question instead
            # of answering 'how many days?'. A stale trip Q&A must never
            # swallow a fresh query.
            intent = self._classify(text)
            if intent:
                session["step"] = None
                self._save()
                return self._run_intent(number, session, intent, text)
            return i18n.t(lang, "days_invalid")
        session["trip_days"] = days
        d_off = self._parse_day_offset(text)
        if d_off:
            session["day"] = d_off
        boat, cat = kochi.resolve_boat(text)  # user may name boat in same message
        if boat:
            session["boat"], session["cat"] = boat, cat
            session["step"] = None
            self._save()
            return self._final_answer(number, session, session["intent"], text) + (
                "\n\n" + i18n.t(lang, "ask_more"))
        session["step"] = "ask_boat"
        self._save()
        return self._boat_question_hint(session, lang)

    def _handle_boat_reply(self, number, session, text):
        lang = session.get("lang") or "en"
        d_off = self._parse_day_offset(text)
        if d_off:
            session["day"] = d_off
        if self._is_same(text) and session.get("boat"):
            pass  # keep the remembered boat (the 'same' shortcut)
        elif any(t in text for t in ("default", "auto", "any", "skip")):
            session["boat"], session["cat"] = "gill netter", "motorized"
        else:
            boat, cat = kochi.resolve_boat(text)
            if not boat:
                if self._is_same(text):
                    return i18n.t(lang, "boat_invalid")  # nothing stored to reuse
                # Not a boat name -> the user probably asked a NEW question
                # while the bot was waiting for the boat type (e.g. they typed
                # 'is it safe to go to sea tomorrow' instead of a boat).
                # Re-classify and answer the fresh query - never swallow it.
                intent = self._classify(text) or self._fuzzy_intent(text)
                if intent:
                    session["step"] = None
                    self._save()
                    return self._run_intent(number, session, intent, text)
                return i18n.t(lang, "boat_invalid")
            session["boat"], session["cat"] = boat, cat
        # combined replies like 'trawler, 2 days' also update the trip length
        d = self._parse_days(text)
        if d and 1 <= d <= 10:  # ignore stray digits (e.g. '25 hp outboard')
            session["trip_days"] = d
        session["step"] = None
        self._save()
        return self._final_answer(number, session, session["intent"], text)
# re-answer helper (used after a language switch) ----------------------------
    def _reanswer(self, number, session, fallback_text=""):
        """Re-answer the last question in the session's (new) language."""
        lang = session.get("lang") or "en"
        intent = session.get("last")
        text = session.get("last_text") or fallback_text or ""
        if not intent:
            return kochi.answer_menu(lang)
        if intent in TRIP_CONTEXT_INTENTS:
            if session.get("boat"):
                return self._final_answer(number, session, intent)
            session["intent"] = intent
            session["step"] = "ask_days"
            self._save()
            return i18n.t(lang, "days_question")
        return self._direct_answer(number, session, intent, text)

# output builders ---------------------------------------------------------
    def _final_answer(self, number, session, intent, text=""):
        lang = session.get("lang") or "en"
        td = session["trip_days"]
        boat = session["boat"] or "gill netter"
        day = session.get("day") or 1
        if intent == "pfz":
            body = kochi.answer_pfz(boat, td, lang, day)
        elif intent == "safety":
            body = kochi.answer_safety(boat, td, lang, day)
        elif intent == "route":
            body = kochi.answer_route(boat, td, lang, day)
        else:
            body = kochi.answer_menu(lang)
        session["intent"] = intent
        session["offers"] = list(OFFERS.get(intent, []))
        session["last"] = intent
        session["step"] = None  # answering always closes a pending Q&A
        # Map overlay for the reply: route -> dashed safe-route map,
        # pfz -> fishing-zone map, everything else -> no map.
        session["map_kind"] = ("route" if intent == "route" else
                               "zone" if intent == "pfz" else None)
        if text:
            session["last_text"] = text
        self._save()
        return body + self._followup_line(intent, lang)

    def _direct_answer(self, number, session, intent, text):
        lang = session.get("lang") or "en"
        if intent == "conditions":
            day = self._day_offset(text)
            session["day"] = day  # follow-up offers inherit the asked day
            body = kochi.answer_conditions(day, lang)
        elif intent == "alerts":
            body = kochi.answer_alerts(lang)
        elif intent == "productivity":
            body = kochi.answer_productivity(text, lang)
        elif intent == "avoid":
            body = kochi.answer_avoid(lang)
        elif intent == "call":
            body = i18n.t(lang, "call")
        else:
            body = kochi.answer_menu(lang)
        session["intent"] = intent
        session["offers"] = list(OFFERS.get(intent, []))
        session["last"] = intent
        session["step"] = None  # any direct/menu answer cancels a pending Q&A
        # avoid -> red restricted-areas map overlay; everything else nothing.
        session["map_kind"] = "avoid" if intent == "avoid" else None
        if text:
            session["last_text"] = text
        self._save()
        return body + self._followup_line(intent, lang)

    def map_context(self, number):
        """Map info for the last reply: (kind, zone, day).
        kind: 'route' | 'zone' | 'avoid' | None. Consumed once by the caller."""
        sess = self.sessions.get(number)
        if not sess:
            return None, None, None
        kind = sess.get("map_kind") or None
        sess["map_kind"] = None  # consumed once by the caller
        if kind in ("route", "zone"):
            cat = sess.get("cat") or "motorized"
            td = sess.get("trip_days") or 1
            day = sess.get("day") or 1
            zone = kochi.select_zone(cat, td, day)
            return kind, zone, day
        return kind, None, None

    @staticmethod
    def _followup_line(intent, lang="en"):
        offers = OFFERS.get(intent, [])
        if not offers:
            return ""
        chips = " / ".join(f"*{o}*" for o in offers)
        return "\n\n" + i18n.t(lang, "offers", chips=chips)

    def reset_all(self):
        self.sessions.clear()
        self._save()


def run_demo():
    """Offline REPL - chat with the bot without WhatsApp/ngrok."""
    bot = Router()
    print("=" * 56)
    print("KOCHI MARINE BOT - conversational offline demo (Ctrl-C to quit)")
    print("Try: 'pfz today' | 'route' | 'tide tomorrow' | 'thank you' | 'yes'")
    print("=" * 56)
    while True:
        try:
            msg = input("\n🧑‍🌾 fisherman> ")
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break
        if not msg.strip():
            continue
        print("🤖 bot:")
        print(bot.handle("demo", msg))


if __name__ == "__main__":
    run_demo()