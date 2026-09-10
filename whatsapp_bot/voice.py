"""
voice.py - WhatsApp voice-note support: download + local speech-to-text.

Fishermen often prefer speaking over typing, so voice notes are transcribed
LOCALLY with faster-whisper (Whisper on CPU, int8) - no API keys, no per
minute cost, works offline once the model is cached on first use.

Env:
  VOICE_MODEL - whisper model size: tiny | base | small (default) | medium.
                'small' is a good Hindi/English accuracy-speed tradeoff.

Meta media download: two-step Graph API (GET /<media-id> -> {url} -> bytes).
The download requires the same Bearer token as sending.
"""

import logging
import os
import tempfile
import threading

import requests

# Hugging Face's xet CDN intermittently 403s model downloads; force the
# classic CDN path BEFORE faster_whisper/huggingface_hub get imported.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

log = logging.getLogger("kochi-bot")

try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:  # voice support is optional at runtime
    WhisperModel = None
    WHISPER_AVAILABLE = False

MODEL_NAME = os.getenv("VOICE_MODEL", "small")
# Pre-downloaded model dir (curl) - avoids HuggingFace CDN flakiness entirely.
LOCAL_MODEL_DIR = os.path.expanduser("~/.cache/whisper-small")

_MODEL = None
_MODEL_LOCK = threading.Lock()

# Replies for voice failures (bilingual so any fisherman understands).
UNCLEAR_REPLY = (
    "🎙️ Sorry, I couldn't understand the voice note 😕.\n"
    "Please type your question, or record it again near the mic.\n\n"
    "🎙️ आवाज़ समझ नहीं आई। कृपया अपना सवाल टाइप करें या पास बैठकर दोबारा बोलें।"
)
FAILED_REPLY = (
    "🎙️ I had trouble reading that voice note 🙏. Please type your question.\n\n"
    "🎙️ वॉयस नोट पढ़ने में दिक्कत हुई। कृपया अपना सवाल टाइप करें।"
)


def available() -> bool:
    """True when faster-whisper is installed."""
    return WHISPER_AVAILABLE


def _get_model():
    """Lazy-load the whisper model once (thread-safe)."""
    global _MODEL
    if not WHISPER_AVAILABLE:
        raise RuntimeError("faster-whisper is not installed")
    with _MODEL_LOCK:
        if _MODEL is None:
            if os.path.exists(os.path.join(LOCAL_MODEL_DIR, "model.bin")):
                source = LOCAL_MODEL_DIR  # pre-downloaded, fully offline
            else:
                source = MODEL_NAME       # hub id (downloads on first use)
            log.info("Loading whisper model %r (first use may download it)...",
                     source)
            _MODEL = WhisperModel(source, device="cpu", compute_type="int8")
            log.info("Whisper model %r ready.", source)
    return _MODEL


def preload() -> bool:
    """Warm the model up at boot so the first voice note replies fast."""
    try:
        _get_model()
        return True
    except Exception as exc:  # pragma: no cover - depends on install state
        log.warning("Voice model preload failed: %s", exc)
        return False


def download_meta_media(media_id: str) -> str:
    """
    Download a WhatsApp voice note (audio) by its media id.

    Returns the local file path; raises RuntimeError on failure.
    """
    from meta import GRAPH_URL, _access_token  # avoid a circular import

    headers = {"Authorization": f"Bearer {_access_token()}"}
    info = requests.get(f"{GRAPH_URL}/{media_id}", headers=headers, timeout=15)
    if not info.ok:
        raise RuntimeError(f"media lookup failed HTTP {info.status_code}")
    media_url = info.json().get("url")
    if not media_url:
        raise RuntimeError("media lookup returned no url")

    blob = requests.get(media_url, headers=headers, timeout=30)
    if not blob.ok:
        raise RuntimeError(f"media download failed HTTP {blob.status_code}")

    out_dir = os.path.join(tempfile.gettempdir(), "kbot_audio")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"audio_{media_id}.ogg")
    with open(path, "wb") as fh:
        fh.write(blob.content)
    return path


def cleanup(path: str):
    """Best-effort removal of a downloaded audio temp file."""
    try:
        os.remove(path)
    except OSError:
        pass


def transcribe_audio(path: str) -> tuple:
    """
    Speech-to-text via faster-whisper (auto-detects Hindi/English per note).

    Returns (text, language_code) e.g. ("pfz today", "en").
    Raises RuntimeError when transcription is unavailable.
    """
    model = _get_model()
    # vad_filter trims silence/noise - helps with harbour & mic noise.
    segments, info = model.transcribe(path, beam_size=1, vad_filter=True)
    parts = []
    total = 0
    for seg in segments:
        piece = seg.text.strip()
        if piece:
            parts.append(piece)
            total += len(piece)
        if total > 500:  # keep very long notes from flooding the chat
            break
    return " ".join(parts), getattr(info, "language", None)
