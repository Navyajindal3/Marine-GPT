"""
greenapi.py - GREEN-API WhatsApp adapter (FREE, no Facebook/Meta business needed).

Why this exists: Meta's Cloud API needs a business portfolio, and brand-new
Facebook accounts are temporarily blocked from creating one. GREEN-API
(green-api.com) gives a FREE developer instance that links to a personal
WhatsApp exactly like WhatsApp Web (scan a QR) - real two-way chat,
webhook support, zero cost, no Meta business needed.

IMPORTANT: Green API's WAF blocks Python HTTP clients (requests/urllib/httpx)
with a TLS-fingerprint 403 while curl from the same machine succeeds, so all
API calls here go through the `curl` binary via subprocess.

Env (.env):
  GREENAPI_ID_INSTANCE  - instance id from the green-api.com console
  GREENAPI_API_TOKEN    - instance api token from the same console
  GREENAPI_API_URL      - per-instance api url, e.g. https://7105.api.greenapi.com

Webhook (set via setSettings or the console):
  webhookUrl      = https://<ngrok>/webhook/greenapi
  incomingWebhook = yes
"""

import json
import logging
import os
import subprocess

log = logging.getLogger("kochi-bot")

TIMEOUT = 15


def greenapi_configured() -> bool:
    """True when GREENAPI_ID_INSTANCE and GREENAPI_API_TOKEN are set."""
    return bool(os.getenv("GREENAPI_ID_INSTANCE") and os.getenv("GREENAPI_API_TOKEN"))


def _base_url() -> str:
    api_url = os.getenv("GREENAPI_API_URL", "https://api.green-api.com").rstrip("/")
    return (f"{api_url}/waInstance{os.getenv('GREENAPI_ID_INSTANCE')}"
            f"/{os.getenv('GREENAPI_API_TOKEN')}")


def _curl_json(method: str, url: str, payload=None) -> tuple:
    """
    HTTP via the curl binary (python TLS fingerprints get 403 from Green API).

    Returns (http_status, parsed_body_or_raw_text).
    """
    cmd = ["curl", "-s", "-X", method,
           "-H", "Content-Type: application/json",
           "--max-time", str(TIMEOUT),
           "-w", "\n%{http_code}"]
    if payload is not None:
        cmd += ["-d", json.dumps(payload)]
    cmd.append(url)
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          timeout=TIMEOUT + 5)
    body, _, code = proc.stdout.rpartition("\n")
    try:
        status = int(code.strip())
    except ValueError:
        status = 0
    if status == 0:
        raise RuntimeError(
            f"GREEN-API call failed (no HTTP status): {proc.stdout[:200]} "
            f"{proc.stderr[:200]}")
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        data = body
    return status, data


def get_qr() -> str:
    """
    Fetch the WhatsApp linking QR for this instance (base64 png data URL).

    Scan it with the phone that should BE the bot:
      WhatsApp -> Settings -> Linked devices -> Link a device.
    """
    status, data = _curl_json("GET", f"{_base_url()}/qr")
    if status >= 400:
        raise RuntimeError(f"QR fetch failed HTTP {status}: {str(data)[:200]}")
    return data.get("message", "") if isinstance(data, dict) else ""


def parse_inbound(payload: dict) -> tuple:
    """
    Extract (phone_digits, text) from a GREEN-API incoming notification.

    Handles BOTH shapes Green API sends:
      wrapped: {"type":"incoming","senderData":{"chatId":...},
                "messageData":{"typeMessage":"text",
                               "textMessageData":{"textMessage":...}}}
      flat:    {"type":"incoming","typeMessage":"textMessage","chatId":...,
                "textMessage":"..."}   (newer shards use this)

    Returns (None, None) for outgoing/status/media/group notifications so the
    bot never loops on its own sends.
    """
    try:
        if payload.get("type") != "incoming":
            return None, None
        chat_id = ""
        text = ""

        if "messageData" in payload:  # wrapped webhook format
            message_data = payload.get("messageData") or {}
            if message_data.get("typeMessage") != "text":
                return None, None
            text = ((message_data.get("textMessageData") or {})
                    .get("textMessage") or "").strip()
            chat_id = (payload.get("senderData") or {}).get("chatId") or ""
        else:  # flat format (newer shards)
            if payload.get("typeMessage") not in ("textMessage", "text"):
                return None, None
            text = (payload.get("textMessage") or "").strip()
            chat_id = payload.get("chatId") or ""

        if not text or not chat_id or chat_id.endswith("@g.us"):
            return None, None  # groups are out of scope for the demo
        return chat_id.split("@")[0], text
    except (AttributeError, TypeError):
        return None, None


def send_message(phone_digits: str, text: str):
    """
    Send a WhatsApp text via GREEN-API sendMessage.

    Returns the idMessage on success; raises RuntimeError on failure.
    """
    chat_id = f"{phone_digits}@c.us"
    url = f"{_base_url()}/sendMessage"
    status, data = _curl_json("POST", url,
                              {"chatId": chat_id, "message": text})
    if status >= 400:
        raise RuntimeError(
            f"GREEN-API send failed HTTP {status}: {str(data)[:200]}")
    return data.get("idMessage") if isinstance(data, dict) else None


def send_file_url(phone_digits: str, file_url: str, caption: str = ""):
    """
    Send a MAP IMAGE via GREEN-API sendFileByUrl (route/zone overlays).

    Green API downloads the file from the PUBLIC url and delivers it as a
    WhatsApp media message. Returns idMessage; raises RuntimeError on failure.
    """
    chat_id = f"{phone_digits}@c.us"
    url = f"{_base_url()}/sendFileByUrl"
    payload = {
        "chatId": chat_id,
        "url": file_url,
        "fileName": "tarang-map.jpg",
    }
    if caption:
        payload["caption"] = caption
    status, data = _curl_json("POST", url, payload)
    if status >= 400:
        raise RuntimeError(
            f"GREEN-API sendFileByUrl failed HTTP {status}: {str(data)[:200]}")
    return data.get("idMessage") if isinstance(data, dict) else None
