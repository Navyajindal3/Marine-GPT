import os
import logging
import langdetect
from orca.state import MarineQueryState

logger = logging.getLogger(__name__)

def bhashini_translate(text: str, source_lang: str, target_lang: str) -> str:
    api_key = os.getenv("BHASHINI_API_KEY")
    if not api_key or api_key == "your_bhashini_api_key_here":
        raise NotImplementedError("TODO: BHASHINI_API_KEY not set")
    logger.warning("STUB: returning placeholder Bhashini translation, real implementation missing")
    return f"[Bhashini translated: {text}]"

def google_translate(text: str, source_lang: str, target_lang: str) -> str:
    credentials = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    logger.warning("STUB: returning placeholder translation, GOOGLE_APPLICATION_CREDENTIALS not configured")
    return f"[Google translated: {text}]"

def detect_language_fast(text: str) -> str:
    if not text or not text.strip():
        return "en"
    try:
        return langdetect.detect(text)
    except langdetect.lang_detect_exception.LangDetectException:
        return "en"

def translate_text(text: str, source_lang: str, target_lang: str) -> str:
    if source_lang == target_lang:
        return text
    try:
        return bhashini_translate(text, source_lang, target_lang)
    except (TimeoutError, ConnectionError, NotImplementedError) as e:
        return google_translate(text, source_lang, target_lang)

def translate_response(text: str, target_lang: str) -> str:
    return translate_text(text, source_lang="en", target_lang=target_lang)

def language_node(state: MarineQueryState) -> MarineQueryState:
    raw_query = state.get("raw_query", "")
    lang = detect_language_fast(raw_query)
    state["detected_language"] = lang
    translated = translate_text(raw_query, lang, "en")
    
    if "[Google translated:" in translated or "[Bhashini translated:" in translated:
        logger.warning(f"TRIPWIRE: Fake translation detected in pipeline for query '{raw_query}'")
        
    state["translated_query"] = translated
    return state
