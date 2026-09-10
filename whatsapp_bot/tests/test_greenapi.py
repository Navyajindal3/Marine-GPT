"""GREEN-API adapter tests (free WhatsApp, no Meta business needed)."""
import json as _json


def _inbound(text="pfz today", chat_id="919311525276@c.us", ntype="incoming",
             type_message="text"):
    return {
        "type": ntype,
        "idMessage": "ABC123",
        "senderData": {"chatId": chat_id, "senderName": "Mehak"},
        "messageData": {"typeMessage": type_message,
                        "textMessageData": {"textMessage": text}},
    }


def test_greenapi_parse_inbound_text():
    import greenapi

    phone, text = greenapi.parse_inbound(_inbound("pfz today"))
    assert phone == "919311525276"
    assert text == "pfz today"


def test_greenapi_parse_inbound_flat_format():
    """Newer Green API shards send this flat shape (seen in production)."""
    import greenapi

    flat = {"type": "incoming", "idMessage": "3B1B5030",
            "timestamp": 1788802511, "typeMessage": "textMessage",
            "chatId": "919311525247@c.us", "textMessage": "pfz today",
            "senderId": "919311525247@c.us", "senderName": "Aryan"}
    phone, text = greenapi.parse_inbound(flat)
    assert phone == "919311525247"
    assert text == "pfz today"


def test_greenapi_ignores_outgoing_media_groups():
    import greenapi

    # our own outgoing sends -> no loop
    assert greenapi.parse_inbound(_inbound(ntype="outgoing")) == (None, None)
    # media message
    assert greenapi.parse_inbound(_inbound(type_message="imageMessage")) == (None, None)
    # group chat
    assert greenapi.parse_inbound(
        _inbound(chat_id="120363@g.us")) == (None, None)
    # garbage
    assert greenapi.parse_inbound({}) == (None, None)


def test_greenapi_send_message(monkeypatch):
    """send_message goes through the curl binary (Green API 403s python TLS)."""
    import subprocess

    import greenapi

    captured = {}

    class FakeProc:
        stdout = '{"idMessage": "MSGID1"}\n200'
        stderr = ""

    def fake_run(cmd, capture_output=None, text=None, timeout=None):
        captured["cmd"] = cmd
        return FakeProc()

    monkeypatch.setenv("GREENAPI_ID_INSTANCE", "1101000000")
    monkeypatch.setenv("GREENAPI_API_TOKEN", "tok123")
    monkeypatch.setenv("GREENAPI_API_URL", "https://7105.api.greenapi.com")
    monkeypatch.setattr(greenapi.subprocess, "run", fake_run)

    mid = greenapi.send_message("919311525276", "Hello fisher!")
    assert mid == "MSGID1"
    cmd = captured["cmd"]
    assert cmd[0] == "curl"
    url = cmd[-1]
    assert url == ("https://7105.api.greenapi.com"
                   "/waInstance1101000000/tok123/sendMessage")
    payload_idx = cmd.index("-d")
    payload = _json.loads(cmd[payload_idx + 1])
    assert payload["chatId"] == "919311525276@c.us"
    assert payload["message"] == "Hello fisher!"


def test_greenapi_send_message_raises_on_error(monkeypatch):
    import greenapi

    class FakeProc:
        stdout = "Forbidden\n403"
        stderr = ""

    monkeypatch.setenv("GREENAPI_ID_INSTANCE", "1101000000")
    monkeypatch.setenv("GREENAPI_API_TOKEN", "tok123")
    monkeypatch.setattr(greenapi.subprocess, "run",
                        lambda *a, **k: FakeProc())
    try:
        greenapi.send_message("919311525276", "nope")
        raised = False
    except RuntimeError as exc:
        raised = "403" in str(exc)
    assert raised


def test_greenapi_webhook_end_to_end(monkeypatch):
    """Full loop: GREEN-API POST -> router -> mocked send -> days question."""
    sent = {}
    monkeypatch.setenv("GREENAPI_ID_INSTANCE", "1101000000")
    monkeypatch.setenv("GREENAPI_API_TOKEN", "tok123")

    import greenapi as greenapi_mod

    def fake_send(phone, text):
        sent["to"], sent["body"] = phone, text
        return "MSGID2"

    monkeypatch.setattr(greenapi_mod, "send_message", fake_send)

    from bot import app as flask_app

    phone = "918888822222"  # unique per test-suite (router remembers trips)
    resp = flask_app.test_client().post(
        "/webhook/greenapi",
        data=_json.dumps(_inbound("Pfz today", chat_id=f"{phone}@c.us")),
        content_type="application/json")
    assert resp.status_code == 200
    assert sent["to"] == phone
    assert "day" in sent["body"].lower()  # asks trip days first

    resp2 = flask_app.test_client().post(
        "/webhook/greenapi",
        data=_json.dumps(_inbound("2 days trawler", chat_id=f"{phone}@c.us")),
        content_type="application/json")
    assert resp2.status_code == 200
    assert "zone" in sent["body"].lower() or "PFZ" in sent["body"]


def test_greenapi_webhook_get_ok():
    from bot import app as flask_app

    resp = flask_app.test_client().get("/webhook/greenapi")
    assert resp.status_code == 200
    assert resp.data.decode() == "OK"
