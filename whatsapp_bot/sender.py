"""
sender.py - proactive / outbound WhatsApp messages via Twilio REST API.

Used by bot.py's /send debug endpoint (and useful later for scheduled
broadcasts like daily PFZ bulletins). Optional dependency on twilio.

NOTE (WhatsApp Sandbox): outbound messages REQUIRE the sandbox's approved
ContentSid (the content/template id of the free "Try it Out" message).
Set TWILIO_WHATSAPP_CONTENT_SID in .env to the content sid shown in the
Twilio sandbox console, otherwise delivery will fail with
"ContentSid Required" (error 21654).
"""

import os
from dotenv import load_dotenv

load_dotenv()


def twilio_available() -> bool:
    """True when the twilio lib AND real credentials are configured."""
    try:
        import twilio  # noqa: F401
    except ImportError:
        return False
    sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    return bool(sid and not sid.startswith("ACxx") and token and token != "your_auth_token")


def send_whatsapp(to_number: str, message: str):
    """
    Send an outbound WhatsApp message to `to_number` (digits only or E.164).
    Returns the Twilio message object (has .sid).
    """
    from twilio.rest import Client

    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_ = os.getenv("TWILIO_WHATSAPP_NUMBER")
    content_sid = os.getenv("TWILIO_WHATSAPP_CONTENT_SID")
    if not (sid and token and from_):
        raise RuntimeError("Twilio credentials not configured - check .env")

    client = Client(sid, token)
    to = to_number if str(to_number).startswith("+") else "+" + str(to_number).lstrip("+")
    kwargs = {"from_": from_, "to": f"whatsapp:{to}", "body": message}
    # WhatsApp Sandbox requires the approved ContentSid for delivery.
    if content_sid:
        kwargs["content_sid"] = content_sid
    return client.messages.create(**kwargs)