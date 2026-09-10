"""Meta WhatsApp Cloud API adapter tests (the FREE conversational path)."""
import json as _json


def flask_request_args():
    from flask import request
    return request.args


def test_meta_verify_hub_ok(monkeypatch):
    from flask import Flask
    import meta

    # WHATSAPP_VERIFY_TOKEN is the primary var (loaded from .env at import),
    # so tests must patch THAT one, not the META_ fallback.
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "s3cret")
    app = Flask(__name__)
    with app.test_request_context(
        "/webhook/meta?hub.mode=subscribe&hub.verify_token=s3cret&hub.challenge=CH123"
    ):
        status, body = meta.verify_hub(flask_request_args())
    assert status == 200
    assert body == "CH123"


def test_meta_verify_hub_bad_token(monkeypatch):
    from flask import Flask
    import meta

    monkeypatch.setenv("META_VERIFY_TOKEN", "s3cret")
    app = Flask(__name__)
    with app.test_request_context(
        "/webhook/meta?hub.mode=subscribe&hub.verify_token=WRONG&hub.challenge=CH"
    ):
        status, _ = meta.verify_hub(flask_request_args())
    assert status == 403


def test_meta_parse_inbound_text():
    import meta

    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "contacts": [{"wa_id": "919311525276"}],
                    "messages": [{"from": "919311525276", "type": "text",
                                  "text": {"body": "pfz today"}}],
                }
            }]
        }],
    }
    wa_id, text = meta.parse_inbound(payload)
    assert wa_id == "919311525276"
    assert text == "pfz today"


def test_meta_parse_inbound_ignores_status_and_media():
    import meta

    # status callback (no messages key) -> (None, None)
    status_payload = {"entry": [{"changes": [{"value": {"statuses": [{"id": "wamid.X"}]}}]}]}
    assert meta.parse_inbound(status_payload) == (None, None)
    # media message -> (None, None)
    media_payload = {"entry": [{"changes": [{"value": {"messages": [
        {"from": "919311525276", "type": "image", "image": {"id": "1"}}]}}]}]}
    assert meta.parse_inbound(media_payload) == (None, None)
    # garbage -> (None, None)
    assert meta.parse_inbound({}) == (None, None)


def test_meta_webhook_end_to_end(monkeypatch):
    """Full loop through the Flask app: Meta POST -> router -> mocked Graph send."""
    sent = {}
    monkeypatch.setenv("META_ACCESS_TOKEN", "EAAG-test")
    monkeypatch.setenv("META_PHONE_NUMBER_ID", "123456789012345")
    monkeypatch.setenv("META_VERIFY_TOKEN", "s3cret")

    import meta as meta_mod

    def fake_send(wa_id, text):
        sent["to"], sent["body"] = wa_id, text
        return "wamid.test"

    monkeypatch.setattr(meta_mod, "send_message", fake_send)

    from bot import app as flask_app

    phone = "918888811111"  # unique per test-suite (router remembers trips)
    payload = {"entry": [{"changes": [{"value": {"messages": [
        {"from": phone, "type": "text", "text": {"body": "pfz today"}}]}}]}]}
    resp = flask_app.test_client().post(
        "/webhook/meta", data=_json.dumps(payload),
        content_type="application/json")
    assert resp.status_code == 200
    # The router asks the trip-days question before answering PFZ.
    assert "day" in sent["body"].lower()

    # follow-up with days + boat completes the flow
    payload2 = {"entry": [{"changes": [{"value": {"messages": [
        {"from": phone, "type": "text", "text": {"body": "2 days trawler"}}]}}]}]}
    resp2 = flask_app.test_client().post(
        "/webhook/meta", data=_json.dumps(payload2),
        content_type="application/json")
    assert resp2.status_code == 200
    assert "PFZ" in sent["body"] or "Zone" in sent["body"] or "zone" in sent["body"]


def test_meta_webhook_verification_get(monkeypatch):
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "s3cret")
    from bot import app as flask_app

    resp = flask_app.test_client().get(
        "/webhook/meta?hub.mode=subscribe&hub.verify_token=s3cret&hub.challenge=42")
    assert resp.status_code == 200
    assert resp.get_data(as_text=True) == "42"
    assert resp.data.decode() == "42"
