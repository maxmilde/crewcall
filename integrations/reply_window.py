"""Reply window and "job full" message, as a background check started by run_bot.

- An offer without an answer after REPLY_WAIT_MINUTES (default 30) counts as a no;
  then workflow.next_steps decides as usual (ask the next nearest, Facebook post, or tell the owner).
- When a job reaches its headcount, the owner gets one message: "✅ <job> is full: names".
"""
import os
import threading
import time
import traceback

from agent import roster, workflow
from agent.describe import label
from integrations import telegram_bot as bot

CHECK_SECONDS = 5
_asked_at: dict[tuple[str, str], float] = {}  # (shift id, cleaner id) -> when we first saw the open offer
_announced: set[str] = set()  # shifts already reported as full


def wait_minutes() -> float:
    return float(os.getenv("REPLY_WAIT_MINUTES", "30"))


def _expire(now: float) -> list[str]:
    """Mark offers past the window as declined; returns the shift ids that changed."""
    changed = set()
    for e in roster.entries:
        key = (e.shift_id, e.cleaner_id)
        if e.status != "asked":
            _asked_at.pop(key, None)
            continue
        if now - _asked_at.setdefault(key, now) >= wait_minutes() * 60:
            e.status = "declined"
            _asked_at.pop(key)
            changed.add(e.shift_id)
            print(f"  [window] no answer from {roster._name(e.cleaner_id)} for {e.shift_id}: counted as no")
    return sorted(changed)


def _announce_full() -> None:
    for shift in roster.shifts.values():
        if not roster.is_full(shift.id):
            _announced.discard(shift.id)  # reopened (cancellation): report again when full
        elif shift.id not in _announced:
            _announced.add(shift.id)
            names = ", ".join(roster._name(e.cleaner_id) for e in roster._confirmed(shift.id))
            bot.notify_owner(f"✅ {label(shift)} is full: {names}")


def check(now: float | None = None) -> None:
    with workflow.lock:
        changed = _expire(time.time() if now is None else now)
        if changed:
            roster.save()
            workflow.next_steps([roster.shifts[s] for s in changed])
        _announce_full()


def watch() -> threading.Thread:
    def loop() -> None:
        while True:
            try:
                check()
            except Exception:  # never stop the agent over one bad check
                traceback.print_exc()
            time.sleep(CHECK_SECONDS)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    print(f"[window] answers wait {wait_minutes():g} min, then the next nearest are asked")
    return thread
