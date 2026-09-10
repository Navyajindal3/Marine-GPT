"""
i18n.py - tiny bilingual layer (English / हिंदी) for the Kochi marine bot.

Language model:
  * every session stores its language ("en"/"hi"); None = not chosen yet
  * first contact with a greeting or unclear text -> bilingual ask
  * a clear first query (e.g. "pfz today") defaults to English (no friction)
  * Devanagari text on first contact -> Hindi is auto-detected
  * "hindi"/"english" (or हिंदी/अंग्रेज़ी) asks to confirm the switch; on "yes"
    the bot re-answers the last question in the new language
"""
import re

ASK_LANG = (
    "🌐 *Choose your language / अपनी भाषा चुनें:*\n"
    "Reply *1* for English\n"
    "हिंदी के लिए *2* भेजें"
)

HINDI_WORDS = ("hindi", "हिंदी", "हिंदी में")
ENGLISH_WORDS = ("english", "अंग्रेज़ी", "अंग्रेजी", "angrezi", "inglish")

DEVANAGARI_RANGE = range(0x0900, 0x097F + 1)

STRINGS = {
    "en": {
        "lang_set": "✅ English selected! Here's what I can do:",
        "switched": "✅ Switched to English.",
        "switch_cancel": "Okay, staying in English 👍",
        "farewell": "👋 Take care, and safe fishing! Come back anytime. 🐟",
        "days_question": (
            "🗓️ For that I need your trip details first.\n\n"
            "🔹 *How many days* will the trip last?\n"
            "Reply a number (1, 2, 3, ... or e.g. \"2 days trawler\")."),
        "days_invalid": "Please reply a number of days (1, 2, 3, ...) or *menu* to cancel.",
        "boat_invalid": ("I didn't recognise that boat 🛥️. Try: canoe / vallam / "
                         "gill netter / outboard / trawler / purse seiner."),
        "boat_question": ("🛥️ What boat type are you using?\n"
                          "Reply: canoe / vallam / gill netter / outboard / "
                          "trawler / purse seiner\n"
                          "(or 'default' for a coastal motorboat)"),
        "already_lang": "You're already chatting in {langname} 😊",
        "ask_more": "_Ask me anything else anytime 🐟_",
        "offers": "▶️ Want more? Reply {chips} - or just *yes*.",
        "yes_generic": "Sure! What would you like to know? Try *pfz* / *safety* / *tide* / *menu*.",
        "no_generic": "Okay! 👍 Anything else? Type *menu* to see what I can do.",
        "unknown": ("Hmm, I didn't get that 🤔. Type *menu* to see what I can answer, "
                    "or ask e.g. 'pfz today' / 'is it safe to fish?' / 'tide tomorrow?'"),
        "empty": "I didn't catch that 🐟. Type *menu* to see what I can do.",
    },
    "hi": {
        "lang_set": "✅ हिंदी चुन ली! मैं यह बता सकता हूँ:",
        "switched": "✅ हिंदी में बदल गया।",
        "switch_cancel": "ठीक है, अंग्रेज़ी में ही रहते हैं 👍",
        "farewell": "👋 अपना ख्याल रखें, सुरक्षित मछली पकड़! फिर कभी बात करेंगे। 🐟",
        "days_question": (
            "🗓️ इसके लिए पहले आपकी यात्रा की जानकारी चाहिए।\n\n"
            "🔹 यात्रा *कितने दिनों* की है?\n"
            "नंबर भेजें (1, 2, 3, ... या जैसे \"2 din trawler\")।"),
        "days_invalid": "कृपया दिनों की संख्या भेजें (1, 2, 3, ...) या रद्द करने के लिए *menu*।",
        "boat_invalid": ("यह नाव समझ नहीं आई 🛥️। लिखें: canoe / नाव / "
                         "gill netter / outboard / trawler / पर्स सीनर।"),
        "boat_question": ("🛥️ आप कौन सी नाव उपयोग कर रहे हैं?\n"
                          "लिखें: canoe / नाव / gill netter / outboard / "
                          "trawler / पर्स सीनर\n"
                          "(या 'default' — तटीय मोटरबोट)"),
        "already_lang": "आप पहले से {langname} में बात कर रहे हैं 😊",
        "ask_more": "_कुछ भी और पूछें, मैं हाज़िर हूँ 🐟_",
        "offers": "▶️ और जानकारी? {chips} भेजें - या बस *haan/yes*।",
        "yes_generic": "ज़रूर! क्या जानना चाहेंगे? *pfz* / *safety* / *tide* / *menu* भेजें।",
        "no_generic": "ठीक है! 👍 और कुछ? *menu* लिखें।",
        "unknown": ("हम्म, समझ नहीं आया 🤔। *menu* लिखें, या पूछें: "
                    "'pfz today' / 'कल समुद्र जाना सुरक्षित है?' / 'कल का ज्वार'"),
        "empty": "समझ नहीं आया 🐟। *menu* लिखें।",
    },
}


def t(lang, key, **kw):
    """Translate key for lang (falls back to English, then the raw key)."""
    table = STRINGS.get(lang, STRINGS["en"])
    template = table.get(key) or STRINGS["en"].get(key, key)
    return template.format(**kw) if kw else template


def looks_hindi(text):
    """True when the text is mostly Devanagari script."""
    dev = sum(1 for ch in text if ord(ch) in DEVANAGARI_RANGE)
    letters = sum(1 for ch in text if ch.isalpha())
    return letters > 0 and dev / letters >= 0.3


def detect_lang_request(text):
    """'hindi'/हिंदी -> 'hi', 'english'/अंग्रेज़ी -> 'en', else None."""
    if any(w in text for w in HINDI_WORDS):
        return "hi"
    if any(w in text for w in ENGLISH_WORDS):
        return "en"
    return None


def parse_lang_choice(text):
    """Language-menu answer -> 'en'/'hi'; None if unclear."""
    t0 = text.strip()
    if t0 in ("1", "en", "english", "inglish", "angrezi", "अंग्रेज़ी", "अंग्रेजी"):
        return "en"
    if t0 in ("2", "hi", "hindi", "हिंदी", "हिंदी में"):
        return "hi"
    return None


def confirm_switch(current, target):
    """Bilingual confirmation prompt for a language-switch request."""
    if target == "hi":
        return ("🌐 Switch to हिंदी? Reply *yes / haan* - or *no*.\n"
                "(क्या भाषा हिंदी में बदलें? *हाँ* भेजें - नहीं तो *no*)")
    return ("🌐 Switch to English? Reply *yes* - or *no / nahi*.\n"
            "(क्या भाषा English में बदलें? *yes* भेजें - या *no*)")
