"""Simulated workers answer their offers on their own, a few seconds later, so a live run
with only a few real phones still looks like a busy team. Real phones are never touched.

Each simulated worker has a personality in data/sim_replies.json (worker id -> replies in order).
"""
import json
import random
import threading
from pathlib import Path

REPLIES_FILE = Path("data/sim_replies.json")
DEFAULT = ["yes", "no, sorry", "yes please", "sorry, I'm busy then"]
DELAY_SECONDS = (4, 9)
ENABLED = True  # the scripted simulation turns this off and replies itself
_count: dict[str, int] = {}


def _replies() -> dict[str, list[str]]:
    return json.loads(REPLIES_FILE.read_text()) if REPLIES_FILE.exists() else {}


def next_reply(cleaner_id: str) -> str:
    options = _replies().get(cleaner_id) or DEFAULT
    n = _count.get(cleaner_id, 0)
    _count[cleaner_id] = n + 1
    return options[min(n, len(options) - 1)]


def later(action, *args) -> None:
    """Run action(*args) after a short, human-looking delay, in the background."""
    if not ENABLED:
        return
    timer = threading.Timer(random.uniform(*DELAY_SECONDS), action, args)
    timer.daemon = True
    timer.start()
