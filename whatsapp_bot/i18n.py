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
    "*Choose your language / अपनी भाषा चुनें:*\n\n"
    "Reply *1* for English\n"
    "हिंदी के लिए *2* भेजें"
)

HINDI_WORDS = ("hindi", "हिंदी", "हिंदी में")
ENGLISH_WORDS = ("english", "अंग्रेज़ी", "अंग्रेजी", "angrezi", "inglish")

DEVANAGARI_RANGE = range(0x0900, 0x097F + 1)

STRINGS = {
    "en": {
        "lang_set": "*English selected!*\n\nHere's what I can help you with:",
        "switched": "*Switched to English.*",
        "switch_cancel": "Okay, staying in English.",

        "farewell": (
            "Take care and safe fishing!\n\n"
            "Come back anytime."
        ),

        "days_question": (
            "*Trip Details*\n\n"
            "I need your trip details first.\n\n"
            "*How many days will the trip last?*\n"
            "Reply with a number: *1, 2, 3, ...*\n\n"
            "You can also reply with something like *\"2 days trawler\"*."
        ),

        "days_invalid": (
            "Please reply with the *number of days* "
            "(1, 2, 3, ...), or type *menu* to cancel."
        ),

        "boat_invalid": (
            "I didn't recognise that boat type.\n\n"
            "Try: *canoe / vallam / gill netter / outboard / "
            "trawler / purse seiner*."
        ),

        "boat_question": (
            "*Boat Type*\n\n"
            "What boat type are you using?\n\n"
            "*Available options:*\n"
            "• Canoe\n"
            "• Vallam\n"
            "• Gill netter\n"
            "• Outboard\n"
            "• Trawler\n"
            "• Purse seiner\n\n"
            "Or reply *default* for a coastal motorboat."
        ),

        "already_lang": "You're already chatting in *{langname}*.",
        "ask_more": "_Ask me anything else anytime._",

        "same_days_hint": (
            "\n\nReply *same* to reuse your last trip: {detail}."
        ),
        "same_boat_hint": "\n\nReply *same* to reuse: *{boat}*.",

        "offers": (
            "*What would you like to check next?*\n"
            "Reply {chips} or simply *yes*."
        ),

        "yes_generic": (
            "Sure! What would you like to know?\n"
            "Try *pfz*, *safety*, *tide*, or *menu*."
        ),

        "no_generic": (
            "Okay. Anything else?\n"
            "Type *menu* to see what I can help with."
        ),

        "unknown": (
            "I didn't quite understand that.\n\n"
            "Type *menu* to see what I can answer, "
            "or try:\n"
            "• *pfz today*\n"
            "• *is it safe to fish?*\n"
            "• *tide tomorrow?*"
        ),

        "empty": (
            "I didn't catch that.\n"
            "Type *menu* to see what I can help with."
        ),
        "call": (
            "🌊 *TARANG*\n\n"
            "Sure — wait for 2 min for the call from TARANG! 📞\n\n"
            "We'll call you shortly on this number. "
            "Please keep your phone nearby and ensure you can receive calls.\n\n"
            "⏳ If you don't receive a call in 2 minutes, try again or type *menu*."
        ),
    },

    "hi": {
        "lang_set": "*हिंदी चुन ली गई है!*\n\nमैं आपकी इन चीज़ों में मदद कर सकता हूँ:",
        "switched": "*हिंदी में बदल गया।*",
        "switch_cancel": "ठीक है, हिंदी में ही रहते हैं।",

        "farewell": (
            "अपना ख्याल रखें और सुरक्षित मछली पकड़ें!\n"
            "जब चाहें फिर बात करें।"
        ),

        "days_question": (
            "*यात्रा की जानकारी*\n\n"
            "इसके लिए पहले आपकी यात्रा की जानकारी चाहिए।\n\n"
            "*यात्रा कितने दिनों की है?*\n"
            "नंबर भेजें: *1, 2, 3, ...*\n\n"
            "आप *\"2 din trawler\"* जैसा भी लिख सकते हैं।"
        ),

        "days_invalid": (
            "कृपया *यात्रा के दिनों की संख्या* भेजें "
            "(1, 2, 3, ...), या रद्द करने के लिए *menu* लिखें।"
        ),

        "boat_invalid": (
            "मैं इस नाव के प्रकार को पहचान नहीं पाया।\n"
            "लिखें: *canoe / नाव / gill netter / outboard / "
            "trawler / पर्स सीनर*।"
        ),

        "boat_question": (
            "*नाव का प्रकार*\n\n"
            "आप कौन सी नाव उपयोग कर रहे हैं?\n\n"
            "*उपलब्ध विकल्प:*\n"
            "• Canoe\n"
            "• Vallam / नाव\n"
            "• Gill netter\n"
            "• Outboard\n"
            "• Trawler\n"
            "• पर्स सीनर\n\n"
            "या तटीय मोटरबोट के लिए *default* लिखें।"
        ),

        "already_lang": "आप पहले से *{langname}* में बात कर रहे हैं।",
        "ask_more": "_आप जब चाहें कुछ भी और पूछ सकते हैं।_",

        "same_days_hint": (
            "\n\n*same* लिखें — पिछली यात्रा फिर से: {detail}।"
        ),
        "same_boat_hint": "\n\n*same* लिखें — पहले जैसी नाव: *{boat}*।",

        "offers": (
            "*आप आगे क्या देखना चाहेंगे?*\n"
            "{chips} भेजें या बस *yes* लिखें।"
        ),

        "yes_generic": (
            "ज़रूर! आप क्या जानना चाहेंगे?\n"
            "*pfz*, *safety*, *tide* या *menu* भेजें।"
        ),

        "no_generic": (
            "ठीक है। और कुछ पूछना है?\n"
            "क्या-क्या उपलब्ध है देखने के लिए *menu* लिखें।"
        ),

        "unknown": (
            "मैं इसे समझ नहीं पाया।\n\n"
            "मैं क्या-क्या बता सकता हूँ, यह देखने के लिए *menu* लिखें।\n"
            "या ऐसे पूछें:\n"
            "• *pfz today*\n"
            "• *कल समुद्र जाना सुरक्षित है?*\n"
            "• *कल का ज्वार?*"
        ),

        "empty": (
            "मैं आपका संदेश समझ नहीं पाया।\n"
            "क्या-क्या उपलब्ध है देखने के लिए *menu* लिखें।"
        ),
        "call": (
            "🌊 *TARANG*\n\n"
            "ज़रूर — 2 मिनट wait करें, TARANG से कॉल आएगी! 📞\n\n"
            "हम इस नंबर पर जल्द ही कॉल करेंगे। "
            "कृपया अपना फोन पास में रखें और यह सुनिश्चित करें कि आप कॉल receive कर सकते हैं।\n\n"
            "⏳ अगर 2 मिनट में कॉल नहीं मिलती, तो फिर से try करें या *menu* लिखें।"
        ),
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
        return (
            "*हिंदी में बदलें?*\n"
            "Reply *yes / haan* to switch, or *no* to stay in English.\n"
            "क्या भाषा हिंदी में बदलें?"
        )
    return (
        "*Switch to English?*\n"
        "Reply *yes* to switch, or *no / nahi* to stay in Hindi.\n"
        "क्या भाषा English में बदलें?"
    )