# tests/conftest.py - isolate the test suite from the live bot's data.
import os
import tempfile

# bot.py reads KOCHI_SESSIONS_PATH at import time to build its Router.
# Point it at a throwaway file BEFORE any test module imports bot, so tests
# neither read the real user's persisted chats nor corrupt them. (pytest
# always imports conftest.py first, so this is guaranteed to run in time.)
os.environ["KOCHI_SESSIONS_PATH"] = os.path.join(
    tempfile.mkdtemp(prefix="kbot_test_sessions_"), "sessions.json")