"""What the agent did, one line per event, for the live board (data/events.jsonl)."""
import json
from datetime import datetime
from pathlib import Path

EVENTS_FILE = Path("data/events.jsonl")
KINDS = ("request", "offer", "reply", "decision", "skip", "owner", "cancel", "recruit")


def log(kind: str, text: str) -> None:
    EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    line = {"at": datetime.now().strftime("%H:%M:%S"), "kind": kind, "text": text}
    with EVENTS_FILE.open("a") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def clear() -> None:
    EVENTS_FILE.unlink(missing_ok=True)
