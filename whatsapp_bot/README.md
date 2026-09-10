# 🐟 Kochi Marine Info WhatsApp Bot (fake backend, fully conversational)

A **complete, real-time WhatsApp bot** that answers fisherman queries about **Kochi Port**.
It runs on a **fake backend** (hardcoded, realistic-looking data) and a pure **if/else
keyword engine** — no marine APIs, no LLM — yet it feels conversational: it chit-chats,
remembers context, asks follow-ups and keeps the dialogue flowing. Plugs straight into
Twilio WhatsApp, and runs fully offline for development.

> Lives in `whatsapp_bot/` — standalone demo separate from the main ORCA LangGraph
> backend (which needs Python 3.11+ / API keys). This demo runs on plain Python 3.8+.

---

## It answers ALL your Kochi queries

| Ask the bot | Intent | Flow |
|---|---|---|
| "where is the nearest PFZ today?" | `pfz` | asks trip days → boat type → best zone |
| "is it safe to go to sea tomorrow morning?" | `safety` | asks trip days → boat type → verdict by boat limits |
| "what are the tide / weather / waves near Kochi?" | `conditions` | instant tide + sea-state reply |
| "any lightning or cyclone alert?" | `alerts` | instant alert bulletin |
| "which regions have high chlorophyll & SST?" / "why did catch drop?" | `productivity` | chl/SST hot spots + decline reasoning |
| "what's the safest route for my vessel?" | `route` | asks trip days → boat type → waypoints + fuel/ETA |
| "which zones are geofenced / to avoid?" | `avoid` | instant hazard polygons |

Trip-intent queries ask **“How many days?”** then **“What boat?”** — or take a single
combined answer like `2 days trawler`. Malayalam keywords (കടല്, കാറ്റ്, മത്സ്യം…)
are understood (answers stay in English).

### 🗨️ Conversational behaviour
- **Intent scoring** (weighted keywords, multi-word phrases double-weighted, priority
  tie-break) + **typo tolerance** for short queries (`pfze` → PFZ).
- **Context follow-ups** after every answer: *▶️ Want more? Reply route / safety /
  conditions - or just yes.* and a **"yes"** picks the next suggestion automatically.
- **Chit-chat**: thanks, "who are you?", "how are you?", greetings, farewell — all handled.
- **Remembers your boat + trip days** across messages; a bare `route` after a PFZ answer
  works without re-asking.
- **Relative days**: "today", "tomorrow", "day after tomorrow".
- **Sessions persist to JSON** (`sessions.json`) so a chat survives a bot restart.

---

## Files

```
whatsapp_bot/
├── bot.py         # Flask webhook /webhook/whatsapp + /health + /send (Twilio entrypoint)
├── router.py      # conversational intent engine + state machine (+ offline REPL)
├── kochi.py       # THE FAKE BACKEND — all canned Kochi data & answer builders
├── sender.py      # proactive/outbound WhatsApp via Twilio REST (/send)
├── requirements.txt
├── .env.example
└── tests/         # test_bot.py (routing/dialogue) + test_webhook.py (Flask client)
```

---

## Quickstart (offline — no Twilio needed)

```bash
cd whatsapp_bot
python3 -m pip install -r requirements.txt     # flask, twilio, python-dotenv, pytest

# 1) Chat in your terminal (real-time, fake backend)
python3 router.py

# 2) Run the tests
python3 -m pytest tests/ -v                    # 25 passed

# 3) Run the webhook + curl it (KOCHI_FORCE_JSON=1 returns readable JSON)
KOCHI_FORCE_JSON=1 python3 bot.py
curl -X POST http://localhost:5000/webhook/whatsapp \
  -d "From=whatsapp:+919000000001&Body=pfz today"
curl -X POST http://localhost:5000/webhook/whatsapp \
  -d "From=whatsapp:+919000000001&Body=2 days trawler"
```

Startup prints a config banner confirming your Twilio SID/From-number are detected.

---

## Go live on WhatsApp (Twilio — your free trial works)

Prereq: a free Twilio account. The 30-day trial gives you a **WhatsApp Sandbox** number
(no credit card, no number purchase).

1. **Get credentials** in the [Twilio console](https://console.twilio.com):
   Console Dashboard → **Account SID + Auth Token**; then
   Messaging → *Try It Out → Send a WhatsApp message* → note the **Sandbox number**
   and its **join code**.
2. **Put them in `.env`** (`cp .env.example .env`), fill:
   `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_NUMBER`,
   `TWILIO_SANDBOX_JOIN_CODE`.
3. **Start the bot** (Twilio lib already in requirements):
   ```bash
   python3 bot.py          # serves on 0.0.0.0:5000
   ```
4. **Tunnel to the internet** (second terminal):
   ```bash
   ngrok http 5000         # -> https://xxxx.ngrok.io
   ```
5. **Point Twilio at your bot:** WhatsApp sandbox → *"When a message comes in"* →
   set webhook to `https://<your-ngrok>/webhook/whatsapp` (POST). Save.
6. **Join the sandbox once** from the fisherman's phone: message `join <code>` to the
   sandbox number. After that, chat in real time.

Optional hardening: set `TWILIO_VERIFY_SIGNATURE=1` in `.env` to cryptographically verify
inbound `X-Twilio-Signature` headers.

### Proactive / broadcast endpoint
`POST /send` with JSON `{"to": "+91…", "body": "…"}` pushes an outbound WhatsApp message
using your sandbox number (`sender.py`). Useful for daily PFZ bulletins later.

> ⚠️ Twilio **trial** limit: the bot can only message numbers that have joined your
> sandbox — expected and fine for a hackathon/demo.
>
> ⚠️ All marine data is **fake demo data** (`kochi.py`); messages are tagged so nobody
> plans a real voyage on it.

---

## Extending to the real ORCA backend

- Keep `bot.py`'s webhook the same and swap `kochi.py`'s answer builders for real data
  agents / the ORCA decision engine. The router already mirrors the ORCA intent list
  (`pfz_lookup`, `safety_check`, `conditions_lookup`, `alert_check`, `route_plan`,
  `productivity_query`) and the `GEAR_TO_PROPULSION` boat mapping.
- Per-phone sessions are JSON-persisted by default; swap `Router(persist_path=…)`'s
  storage for Redis (keyed by `wa_id`) when you scale.
- Intent scoring lives in `router.INTENT_KEYWORDS` / `OFFERS` — extend those tables to
  teach the bot new questions without touching the fake backend.