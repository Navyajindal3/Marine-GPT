"""
bot.py - Twilio WhatsApp webhook entrypoint for the Kochi Marine Info Bot.

Complete & production-shaped demo:
  - synchronous TwiML reply for fast (real-time) answers
  - optional X-Twilio-Signature verification
  - media handling (images/files -> asks for text)
  - session persistence via JSON (KOCHI_SESSIONS_PATH)
  - /send endpoint for proactive/outbound messages (dev/test)

Run:      python bot.py        (then `ngrok http 5000` -> Twilio sandbox webhook)
Test:     curl -X POST "http://localhost:5000/webhook/whatsapp" \\
             -H "Content-Type: application/x-www-form-urlencoded" \\
             -d "From=whatsapp:+919000000001&Body=pfz today"
"""

import logging
import os
import threading

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file

from router import Router
from sender import send_whatsapp, twilio_available
import meta
import greenapi
import voice
import mapgen

load_dotenv()

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("kochi-bot")

app = Flask(__name__)

# Sessions persist across restarts so a chat can resume later.
bot = Router(persist_path=os.getenv("KOCHI_SESSIONS_PATH", "sessions.json"))

try:
    from twilio.request_validator import RequestValidator
    from twilio.twiml.messaging_response import MessagingResponse
    HAS_TWILIO = True
except ImportError:  # pragma: no cover
    HAS_TWILIO = False

VERIFY = os.getenv("TWILIO_VERIFY_SIGNATURE", "").lower() in ("1", "true", "yes")


def _validator():
    """Build a Twilio RequestValidator only when real creds exist."""
    if not HAS_TWILIO:
        return None
    sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    if sid.startswith("ACxx") or token == "your_auth_token" or not sid:
        return None
    return RequestValidator(token)


@app.route("/health")
def health():
    return jsonify(status="ok", bot="kochi-marine", sessions=len(bot.sessions))


# Public base URL (ngrok or env override) used to build absolute map-image
# URLs that Twilio/Meta/Green-API can download.
_public_base = None


def _public_base_url():
    """https://<ngrok-host> - discovered from the running ngrok or TARANG_PUBLIC_URL."""
    global _public_base
    if _public_base:
        return _public_base
    override = os.getenv("TARANG_PUBLIC_URL", "").strip().rstrip("/")
    if override:
        _public_base = override
        return _public_base
    try:  # read the live ngrok tunnel (already running for the webhooks)
        import requests as _rq
        tunnels = _rq.get("http://127.0.0.1:4040/api/tunnels", timeout=2).json()
        for t in tunnels.get("tunnels", []):
            if "https" in t["public_url"]:
                _public_base = t["public_url"].rstrip("/")
                return _public_base
    except Exception:
        pass
    return ""


@app.route("/map/<path:fn>")
def map_file(fn):
    """Serve a generated map image (https available via the ngrok tunnel)."""
    from os.path import basename
    path = os.path.join(mapgen.TMP, basename(fn))
    if not os.path.exists(path):
        return jsonify(error="map not found"), 404
    return send_file(path, mimetype="image/jpeg", max_age=3600)


def _render_map(kind, zone, day):
    """Build the map image for a reply; returns (filename, caption) or None."""
    try:
        if kind == "route" and zone:
            path, cap = mapgen.render_route_map(zone)
        elif kind == "zone" and zone:
            path, cap = mapgen.render_zone_map(zone, day)
        elif kind == "avoid":
            path, cap = mapgen.render_avoid_map()
        else:
            return None
        return os.path.basename(path), cap
    except Exception as exc:  # never let a map failure kill the chat reply
        log.warning("Map render failed: %s", str(exc)[:120])
        return None


def _attach_map_if_needed(phone):
    """After bot.handle(): render + return {kind, filename, caption, url} or None."""
    if os.getenv("KOCHI_MAPS", "1") != "1":
        return None
    kind, zone, day = bot.map_context(phone)
    if not kind:
        return None
    base = _public_base_url()   # no public URL -> skip render entirely
    if not base:
        return None
    rendered = _render_map(kind, zone, day)
    if not rendered:
        return None
    fn, caption = rendered
    return {"kind": kind, "filename": fn, "caption": caption,
            "url": f"{base}/map/{fn}"}


@app.route("/webhook/whatsapp", methods=["GET", "POST"])
def whatsapp_webhook():
    if request.method == "GET":
        # Twilio/Sandbox may ping the URL to confirm liveness.
        return "OK", 200

    # Optional security: reject forged requests.
    val = _validator()
    if val and VERIFY:
        signature = request.headers.get("X-Twilio-Signature", "")
        if not val.validate(request.url, request.values, signature):
            log.warning("Rejected bad Twilio signature from %s", request.remote_addr)
            return "Invalid signature", 403

    values = request.values
    from_number = ((values.get("From", "") or "")
                   .replace("whatsapp:", "").strip())
    body = (values.get("Body", "") or "").strip()
    num_media = int(values.get("NumMedia", "0") or 0)

    log.info("IN From=%s Media=%s Body=%r", from_number, num_media, body[:120])

    # Sandbox join message ('join <code>') is handled by Twilio itself.
    # We must NOT reply to it - an empty <Response/> lets Twilio complete the
    # join handshake without us sending a confusing auto-reply to the user.
    if body.lower().startswith("join "):
        log.info("JOIN handshake - returning empty TwiML (no reply sent)")
        if not HAS_TWILIO or os.getenv("KOCHI_FORCE_JSON") == "1":
            return jsonify(reply=""), 200
        return str(MessagingResponse()), 200, {"Content-Type": "text/xml"}

    if num_media > 0:
        reply = ("I can't read images/files just yet 🐟 - "
                 "please type your question as text (e.g. 'pfz today').")
    else:
        reply = bot.handle(from_number, body)

    # Map overlay for route/pfz/avoid replies (linked image - Twilio's sandbox
    # content template can't attach raw media, so the map ships as a link).
    try:
        mp = _attach_map_if_needed(from_number)
        if mp:
            reply += f"\n\n{mp['caption']}\n{mp['url']}"
    except Exception:
        log.warning("Twilio map link failed", exc_info=True)

    # WhatsApp Sandbox nuance: outbound messages (including the reply through the
    # automatic TwiML path) need the approved ContentSid to be delivered. To make
    # our replies reliably reach the user, we send the reply outbound via the REST
    # API with the sandbox-approved content_id from .env (sender.py handles it).
    if from_number and body and not body.lower().startswith("join "):
        from sender import send_whatsapp
        try:
            send_whatsapp(from_number, reply)
            log.info("DELIVERED outbound reply to %s via API/content_sid", from_number)
        except Exception as exc:
            log.warning("API outbound delivery failed (%s) - falling back to TwiML", exc)

    if not HAS_TWILIO or os.getenv("KOCHI_FORCE_JSON") == "1":
        # dev/test / curl debugging -> JSON reply
        return jsonify(reply=reply), 200

    resp = MessagingResponse()
    resp.message(reply)
    log.info("OUT -> %s", reply.splitlines()[0][:60])
    return str(resp), 200, {"Content-Type": "text/xml"}


@app.route("/send", methods=["POST"])


@app.route("/sms", methods=["GET", "POST"])
def sms_webhook():
    """Twilio SMS webhook: fisherman texts the Twilio SMS number -> bot replies by SMS.

    Same brain as WhatsApp (/webhook/whatsapp): shares bot.handle(), sessions,
    i18n (multi-language), and map logic via _attach_map_if_needed(). SMS is
    text-only (no voice notes, no inline media); the map ships as caption + URL
    text (Twilio SMS to a +1 trial number can't send inline JPEGs without MMS).
    """
    if request.method == "GET":
        return "OK", 200

    values = request.values
    from_number = (values.get("From", "") or "").strip()
    body = (values.get("Body", "") or "").strip()

    # Normalise sender to E.164-with-leading-plus so SMS + WhatsApp + Meta all
    # share ONE session per fisherman when they use the same mobile number.
    if from_number and not from_number.startswith("+"):
        from_number = "+" + from_number

    log.info("SMS IN From=%s Body=%r", from_number, body[:120])

    if not from_number or not body:
        # Empty SMS (delivery receipt / idle ping) -> ack with empty TwiML so
        # Twilio doesn't keep retrying.
        return str(MessagingResponse()), 200, {"Content-Type": "text/xml"}

    reply = bot.handle(from_number, body)

    # Map overlay (route / zone / avoid): ship as caption + URL text, same as
    # the WhatsApp TwiML path. SMS can't attach the JPEG inline (would need MMS).
    try:
        mp = _attach_map_if_needed(from_number)
        if mp:
            reply += f"\n\n{mp['caption']}\n{mp['url']}"
    except Exception:
        log.warning("SMS map link failed", exc_info=True)

    resp = MessagingResponse()
    resp.message(reply)
    log.info("SMS OUT -> %s", reply.splitlines()[0][:60])
    return str(resp), 200, {"Content-Type": "text/xml"}


def send_endpoint():
    """Dev/test: send a proactive message. Body: {"to": "...", "body": "..."}"""
    if not twilio_available():
        return jsonify(ok=False, error="twilio not installed or .env missing"), 400
    data = request.get_json(silent=True) or request.values
    to = (data.get("to") or "").strip()
    msg = (data.get("body") or "").strip()
    if not (to and msg):
        return jsonify(ok=False, error="'to' and 'body' are required"), 400
    try:
        sent = send_whatsapp(to, msg)
        return jsonify(ok=True, sid=getattr(sent, "sid", None))
    except Exception as exc:  # pragma: no cover
        log.exception("Outbound send failed")
        return jsonify(ok=False, error=str(exc)), 500


def _process_voice_note(wa_id: str, media_id: str):
    """Download + transcribe a voice note, then reply through the router.

    The transcript is fed into the same bot.handle() path as typed text, so the
    session (any in-flight boat/days question the user just answered by voice) is
    honoured — a second voice note like "2 din" / "तो देज" completes the rung
    instead of re-asking, and an "is it safe to go to sea tomorrow" VN produces
    the safety answer straight away.
    """
    path = None
    try:
        if not voice.available():
            meta.send_message(wa_id,
                              "🎙️ Voice notes aren't enabled on this bot yet — "
                              "please type your question.")
            return
        path = voice.download_meta_media(media_id)
        try:
            text, lang = voice.transcribe_audio(path)
        finally:
            voice.cleanup(path)
            path = None
        if not text or not text.strip():
            log.info("VOICE unclear (%s)", lang)
            meta.send_message(wa_id, voice.UNCLEAR_REPLY)
            return
        text = text.strip()
        log.info("VOICE heard (%s): %r", lang, text)
        reply = bot.handle(wa_id, text)
        mid = meta.send_message(wa_id, reply)
        # Voice-note replies use a small audio-only marker, never a transcript
        # echo - the answer is the reply, not "You said ...".
        log.info("META OUT (voice) -> %s (msg_id=%s)",
                 reply.splitlines()[0][:60], mid)
    except Exception:  # pragma: no cover - network/model failures
        log.exception("Voice-note processing failed")
        try:
            meta.send_message(wa_id, voice.FAILED_REPLY)
        except Exception:
            log.exception("Voice fallback reply also failed")


# ---------------------------------------------------------------------------
# Meta WhatsApp Cloud API (FREE, official, fully conversational)
# ---------------------------------------------------------------------------
@app.route("/webhook/meta", methods=["GET", "POST"])
def meta_webhook():
    """Meta Cloud API webhook: GET = verify handshake, POST = inbound message."""
    if request.method == "GET":
        status, challenge = meta.verify_hub(request.args)
        if status == 200:
            log.info("Meta webhook verified OK")
            return challenge, 200
        log.warning("Meta verify token mismatch")
        return "verify token mismatch", 403

    if not meta.meta_configured():
        log.warning("Meta inbound but META_* env not configured")
        return jsonify(ok=False, error="meta not configured"), 501

    payload = request.get_json(silent=True) or {}
    wa_id, text = meta.parse_inbound(payload)
    if wa_id and text:
        log.info("META IN From=%s body=%r", wa_id, text[:120])
        reply = bot.handle(wa_id, text)
        try:
            mid = meta.send_message(wa_id, reply)
            log.info("META OUT -> %s (msg_id=%s)", reply.splitlines()[0][:60], mid)
        except Exception as exc:  # pragma: no cover
            log.exception("Meta outbound send failed")
            return jsonify(ok=False, error=str(exc)), 500
        # Map overlay (route/zone/avoid) as a proper WhatsApp image message.
        try:
            mp = _attach_map_if_needed(wa_id)
            if mp:
                mid2 = meta.send_image(wa_id, mp["url"], mp["caption"])
                log.info("META MAP -> %s (msg_id=%s)", mp["filename"], mid2)
        except Exception:  # pragma: no cover
            log.warning("Meta map send failed", exc_info=True)
        return jsonify(ok=True), 200

    # Voice note? Ack instantly and process in the background - Meta retries
    # slow webhooks, which would mean duplicate transcriptions/replies.
    audio = meta.parse_inbound_audio(payload)
    if audio and audio[0] and audio[1]:
        audio_wa, media_id = audio
        log.info("META AUDIO From=%s media=%s -> background STT", audio_wa, media_id)
        threading.Thread(target=_process_voice_note, args=(audio_wa, media_id),
                         daemon=True).start()
        return jsonify(ok=True), 200

    # status updates / other media / echo — ack so Meta doesn't retry.
    return jsonify(ok=True), 200


# ---------------------------------------------------------------------------
# GREEN-API adapter (FREE, personal WhatsApp via QR — no Meta business needed)
# ---------------------------------------------------------------------------
@app.route("/webhook/greenapi", methods=["GET", "POST"])
def greenapi_webhook():
    """GREEN-API webhook: inbound notifications -> Router -> sendMessage."""
    if request.method == "GET":
        return "OK", 200

    if not greenapi.greenapi_configured():
        log.warning("GREEN-API inbound but GREENAPI_* env not configured")
        return jsonify(ok=False, error="greenapi not configured"), 501

    payload = request.get_json(silent=True) or {}
    phone, text = greenapi.parse_inbound(payload)
    if not phone or not text:
        # outgoing/status/media notifications — ack so it doesn't retry/loop.
        log.info("GREEN notify skipped: type=%r typeMessage=%r",
                 payload.get("type"), payload.get("typeMessage")
                 or (payload.get("messageData") or {}).get("typeMessage"))
        return jsonify(ok=True), 200

    log.info("GREEN IN From=%s body=%r", phone, text[:120])
    reply = bot.handle(phone, text)
    try:
        mid = greenapi.send_message(phone, reply)
        log.info("GREEN OUT -> %s (msg_id=%s)", reply.splitlines()[0][:60], mid)
    except Exception as exc:  # pragma: no cover
        if "403" in str(exc):
            # Green API free tier throttles bursts of messages (anti-spam).
            # Real usage (a reply per fisherman query) stays well under it.
            log.warning("GREEN OUT throttled (403 rate limit) — "
                        "wait a few minutes between test messages. %s",
                        str(exc)[:120])
        else:
            log.exception("GREEN-API outbound send failed")
        # Ack 200 so Green API doesn't retry-storm and deepen the throttle.
        return jsonify(ok=False, throttled="403" in str(exc)), 200
    # Map overlay (route/zone/avoid) as a media message via sendFileByUrl.
    try:
        mp = _attach_map_if_needed(phone)
        if mp:
            mid2 = greenapi.send_file_url(phone, mp["url"], mp["caption"])
            log.info("GREEN MAP -> %s (msg_id=%s)", mp["filename"], mid2)
    except Exception as exc:  # pragma: no cover
        log.warning("GREEN map send failed: %s", str(exc)[:120])
    return jsonify(ok=True), 200


def _config_summary():
    sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    num = os.getenv("TWILIO_WHATSAPP_NUMBER", "")
    ok = bool(HAS_TWILIO and twilio_available())
    meta_ok = meta.meta_configured()
    voice_state = ("READY (local whisper '" + voice.MODEL_NAME + "')"
                   if voice.available() else
                   "not installed (pip install faster-whisper)")
    lines = [
        "─────────────────────────────────────────",
        "🐟 Kochi Marine Info Bot - WhatsApp webhook",
        f"  Twilio lib:      {'installed' if HAS_TWILIO else 'MISSING (pip install twilio)'}",
        f"  Twilio creds:    {'OK' if ok else 'incomplete - check .env'}",
        f"  SID:             {'**' + sid[-4:] if len(sid) > 4 else '(empty)'}",
        f"  From number:     {num}",
        f"  Twilio sig check:{'ON' if VERIFY else 'OFF'}",
        f"  Meta Cloud API:  {'READY (free, conversational)' if meta_ok else 'not configured (META_* in .env)'}",
        f"  Voice notes:     {voice_state}",
        f"  GREEN-API free:  {'READY (personal WhatsApp, no Meta needed)' if greenapi.greenapi_configured() else 'not configured (GREENAPI_* in .env)'}",
        f"  Sessions file:   {os.getenv('KOCHI_SESSIONS_PATH', 'sessions.json')}",
        "─────────────────────────────────────────",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    print(_config_summary())
    print("  curl test:")
    q = f'http://localhost:{port}/webhook/whatsapp'
    print(f'    curl -X POST "{q}" -d "From=whatsapp%2B919000000001&Body=pfz today"')
    if voice.available():
        log.info("Warming up the voice model in background...")
        threading.Thread(target=voice.preload, daemon=True).start()
    app.run(host="0.0.0.0", port=port, debug=False)