# tests/test_webhook.py - Flask test-client for the webhook (no real Twilio).
import os
import tempfile

import pytest

# Point sessions at a throwaway file & force JSON replies BEFORE importing bot.
_tmp = tempfile.NamedTemporaryFile(delete=False)
os.environ["KOCHI_SESSIONS_PATH"] = _tmp.name
os.environ["KOCHI_FORCE_JSON"] = "1"

import bot  # noqa: E402 - needs env set first


@pytest.fixture(autouse=True)
def clean_sessions():
    bot.bot.sessions.clear()
    yield


@pytest.fixture()
def client():
    bot.app.testing = True
    return bot.app.test_client()


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"


def test_webhook_pfz_flow_roundtrip(client):
    a = client.post("/webhook/whatsapp",
                    data={"From": "whatsapp:+9190000001", "Body": "pfz today"})
    assert a.status_code == 200
    assert "trip details" in a.get_json()["reply"].lower()

    b = client.post("/webhook/whatsapp",
                    data={"From": "whatsapp:+9190000001", "Body": "2 days trawler"})
    assert "PFZ" in b.get_json()["reply"]
    assert "Deep shelf" in b.get_json()["reply"]


def test_webhook_media_as_text_request(client):
    r = client.post("/webhook/whatsapp",
                    data={"From": "whatsapp:+9190000002", "Body": "pfz today",
                          "NumMedia": "1"})
    assert r.status_code == 200
    assert "can't read images" in r.get_json()["reply"]


def test_webhook_get_ok(client):
    assert client.get("/webhook/whatsapp").status_code == 200


# clean up the temp session file
def _remove_tmp():
    try:
        os.unlink(_tmp.name)
    except OSError:
        pass


_remove_tmp()