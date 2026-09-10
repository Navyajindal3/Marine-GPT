# tests/test_voice.py - voice-note pipeline (mocked STT, no model download).
import time

import pytest

import bot
import meta
import voice


AUDIO_PAYLOAD = {
    "entry": [{"changes": [{"value": {"messages": [{
        "from": "919311525276",
        "type": "audio",
        "audio": {"id": "MEDIA123", "mime_type": "audio/ogg; codecs=opus"},
    }]}}]}],
}


# ---- meta audio parsing ------------------------------------------------------
def test_parse_inbound_audio():
    wa_id, media_id = meta.parse_inbound_audio(AUDIO_PAYLOAD)
    assert wa_id == "919311525276"
    assert media_id == "MEDIA123"


def test_parse_inbound_audio_ignores_text_and_status():
    text_payload = {"entry": [{"changes": [{"value": {"messages": [{
        "from": "919311525276",
        "type": "text",
        "text": {"body": "pfz today"},
    }]}}]}]}
    assert meta.parse_inbound_audio(text_payload) == (None, None)
    status_payload = {"entry": [{"changes": [{"value": {"statuses": [
        {"id": "wamid.X", "status": "delivered"}]}}]}]}
    assert meta.parse_inbound_audio(status_payload) == (None, None)


# ---- end-to-end voice flow (transcription mocked) ----------------------------
@pytest.fixture
def voice_env(monkeypatch):
    """Mock download/STT and capture outbound sends."""
    sent = {}
    monkeypatch.setattr(voice, "download_meta_media",
                        lambda media_id: "/tmp/fake_audio.ogg")
    monkeypatch.setattr(voice, "cleanup", lambda path: None)
    monkeypatch.setattr(meta, "send_message",
                        lambda to, body: sent.update(to=to, body=body) or "wamid.1")
    return sent


def test_voice_note_runs_router_and_prefixes_transcript(voice_env, monkeypatch):
    monkeypatch.setattr(voice, "transcribe_audio",
                        lambda path: ("pfz today", "en"))
    bot._process_voice_note("919311525276", "MEDIA123")
    assert voice_env["to"] == "919311525276"
    assert 'pfz today' in voice_env["body"]
    assert "How many days" in voice_env["body"] or "trip details" in voice_env["body"]


def test_voice_note_unclear_gets_friendly_reply(voice_env, monkeypatch):
    monkeypatch.setattr(voice, "transcribe_audio", lambda path: ("  ", "en"))
    bot._process_voice_note("919311525276", "MEDIA123")
    assert voice_env["body"] == voice.UNCLEAR_REPLY


def test_voice_note_hindi_goes_to_hindi_flow(voice_env, monkeypatch):
    monkeypatch.setattr(voice, "transcribe_audio",
                        lambda path: ("कल समुद्र जाना सुरक्षित है", "hi"))
    bot._process_voice_note("919311525276", "MEDIA123")
    assert "सुरक्षित" in voice_env["body"] or "समुद्र" in voice_env["body"]


# ---- webhook route: instant 200 + background processing ----------------------
def test_webhook_audio_returns_200_and_replies_in_background(
        voice_env, monkeypatch):
    monkeypatch.setattr(voice, "transcribe_audio",
                        lambda path: ("what are the tide conditions", "en"))
    client = bot.app.test_client()
    resp = client.post("/webhook/meta", json=AUDIO_PAYLOAD)
    assert resp.status_code == 200
    for _ in range(50):  # background thread: wait up to ~5 s
        if voice_env.get("body"):
            break
        time.sleep(0.1)
    assert "Tide" in voice_env["body"] or "tide" in voice_env["body"].lower()


def test_whisper_library_present():
    """faster-whisper should be installed for voice support."""
    assert voice.available() is True
