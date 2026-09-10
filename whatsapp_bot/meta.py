"""
meta.py - Meta WhatsApp Cloud API adapter (FREE, official, conversational).

Why: the Twilio trial sandbox only delivers pre-approved template messages
(no free dynamic auto-replies). Meta's WhatsApp Cloud API gives FREE real-time
conversational replies (user-initiated, no template needed, 1000 conversations/mo free).

Webhook  (same port/ngrok as the Twilio webhook):
  GET  /webhook/meta?hub.mode=subscribe&hub.verify_token=...&hub.challenge=...
         -> verify handshake (Meta pings this once)
  POST /webhook/meta   -> inbound WhatsApp message  -> our Router  -> send reply
                             back via Graph API with the access token (free, immediate).

Env (.env) - BOTH naming conventions are accepted (Meta tutorial style first):
  WHATSAPP_TOKEN        (or META_ACCESS_TOKEN)     - access token from the Meta app
  WHATSAPP_PHONE_NUMBER_ID (or META_PHONE_NUMBER_ID) - 15-digit id of the bot's number
  WHATSAPP_VERIFY_TOKEN (or META_VERIFY_TOKEN)     - any secret string you choose
                                                   (same value goes in Meta's webhook config)
"""

import logging
import os

import requests  # noqa: F401 - used for Graph API calls

log = logging.getLogger("kochi-bot")

GRAPH_API_VERSION = os.getenv("META_API_VERSION", "v19.0")
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


def _access_token() -> str:
    return (os.getenv("WHATSAPP_TOKEN")
            or os.getenv("META_ACCESS_TOKEN") or "")


def _phone_number_id() -> str:
    return (os.getenv("WHATSAPP_PHONE_NUMBER_ID")
            or os.getenv("META_PHONE_NUMBER_ID") or "")


def _verify_token() -> str:
    return (os.getenv("WHATSAPP_VERIFY_TOKEN")
            or os.getenv("META_VERIFY_TOKEN") or "")


def meta_configured() -> bool:
    """True when access token, phone-number-id and verify token are set."""
    return bool(_access_token() and _phone_number_id() and _verify_token())


def verify_hub(args) -> tuple:

    """
    Handle Meta's webhook verification handshake.

    Returns (http_status, body_text).
    """
    mode = args.get("hub.mode")
    token = args.get("hub.verify_token")
    challenge = args.get("hub.challenge")
    if mode == "subscribe" and token == _verify_token():
        return 200, str(challenge)
    return 403, "verify token mismatch"


def parse_inbound(payload: dict) -> tuple:


    """
    Extract (wa_id, text) from Meta's inbound webhook payload.



    Returns (None, None) for statuses/echoes/media (we only text-chat..
    """
    try:
        value = payload["entry"][0]["changes"][0]["value"]
    except (KeyError, IndexError, TypeError):
        return None, None
    if not value.get("messages"):
        return None, None  # status updates (read/delivered) have no messages key
    # prefer the first TEXT message; skip media/interactive.

    for msg in value["messages"]:
        if msg.get("type") == "text" and msg.get("text", {}).get("body"):
            wa_id = msg["from"]
            text = msg["text"]["body"].strip()
            return wa_id, text
    return None, None


def parse_inbound_audio(payload: dict) -> tuple:
    """
    Extract (wa_id, media_id) from an inbound VOICE NOTE (type "audio").

    Returns (None, None) for everything else, so the text path stays intact.
    """
    try:
        value = payload["entry"][0]["changes"][0]["value"]
    except (KeyError, IndexError, TypeError):
        return None, None
    if not value.get("messages"):
        return None, None
    for msg in value["messages"]:
        if msg.get("type") == "audio":
            audio = msg.get("audio") or {}
            if audio.get("id") and msg.get("from"):
                return msg["from"], audio["id"]
    return None, None


def send_message(wa_id: str, text: str):
    """
    Send a reply via Meta Graph API (free, user-initiated window, no template).
    Returns the message id on success; raises on failure.
    """
    url = f"{GRAPH_URL}/{_phone_number_id()}/messages"
    headers = {
        "Authorization": f"Bearer {_access_token()}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "text",
        "text": {"body": text},
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=12)
    if not resp.ok:
        raise RuntimeError(f"Meta send failed HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    try:
        return data["messages"][0]["id"]
    except (KeyError, IndexError):
        return None