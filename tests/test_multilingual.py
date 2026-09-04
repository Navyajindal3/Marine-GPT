import pytest
import logging
from unittest.mock import patch
from orca.multilingual import (
    detect_language_fast,
    translate_text,
    translate_response,
    language_node,
)

def test_detect_language_fast():
    assert detect_language_fast("Hello how are you?") == "en"
    assert detect_language_fast("வணக்கம்") == "ta" # Tamil, non-English
    assert detect_language_fast("") == "en"
    assert detect_language_fast("   ") == "en"

@patch("orca.multilingual.bhashini_translate")
@patch("orca.multilingual.google_translate")
def test_translate_text_bhashini_success(mock_google, mock_bhashini):
    mock_bhashini.return_value = "Mock Bhashini Translation"
    
    result = translate_text("வணக்கம்", "ta", "en")
    
    assert result == "Mock Bhashini Translation"
    mock_bhashini.assert_called_once_with("வணக்கம்", "ta", "en")
    mock_google.assert_not_called()

@patch("orca.multilingual.bhashini_translate")
@patch("orca.multilingual.google_translate")
def test_translate_text_bhashini_error_fallback(mock_google, mock_bhashini):
    mock_bhashini.side_effect = TimeoutError("Bhashini timed out")
    mock_google.return_value = "Mock Google Translation"
    
    result = translate_text("வணக்கம்", "ta", "en")
    
    assert result == "Mock Google Translation"
    mock_bhashini.assert_called_once_with("வணக்கம்", "ta", "en")
    mock_google.assert_called_once_with("வணக்கம்", "ta", "en")

@patch("orca.multilingual.bhashini_translate")
def test_translate_response_roundtrip(mock_bhashini):
    mock_bhashini.return_value = "Mock translated to Tamil"
    
    result = translate_response("Hello", "ta")
    
    assert result == "Mock translated to Tamil"
    mock_bhashini.assert_called_once_with("Hello", "en", "ta")

def test_translate_text_same_language():
    result = translate_text("Hello", "en", "en")
    assert result == "Hello"

def test_language_node_tripwire(caplog):
    state = {"raw_query": "வணக்கம்"}
    with caplog.at_level(logging.WARNING):
        result = language_node(state)
        
    assert "[Google translated:" in result["translated_query"]
    assert "TRIPWIRE: Fake translation detected in pipeline for query 'வணக்கம்'" in caplog.text
    assert "STUB: returning placeholder translation, GOOGLE_APPLICATION_CREDENTIALS not configured" in caplog.text
