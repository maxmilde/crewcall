"""Scripted run of the demo story with simulated workers, no Telegram or Apify needed.

Run the board in one terminal and this in another:
    .venv/bin/python -m agent.board        # http://localhost:8000
    .venv/bin/python -m agent.simulate     # add --fast to skip the pauses
"""
import sys
import time
from pathlib import Path

import agent.stand_ins as S
from agent import events, roster
from shared.schemas import Request

PAUSE = 0 if "--fast" in sys.argv else 2.5
roster.STATE_FILE.unlink(missing_ok=True)
events.clear()
owner_answers = iter(["2", "2", "2", "yes"])  # headcounts the email leaves open, then go


def owner(question):
    S.notify_owner(question)
    answer = next(owner_answers, "1")
    print(f"     owner> {answer}")
    return answer


S.ask_owner = owner
import agent.workflow as W  # noqa: E402  (after patching ask_owner)
W.ask_owner = owner

roster.load_cleaners_csv()
emails = [("gym", "email1"), ("shop", "email2"), ("event", "email3")]
shifts = W.start([Request(id=rid, raw_text=Path(f"data/requests/{f}.txt").read_text(), received_at="2026-11-13T09:00:00")
                  for rid, f in emails])
time.sleep(PAUSE)
W.staff(shifts)
time.sleep(PAUSE)

event_shifts = [s for s in shifts if s.request_id == "event"]
thu = next(s for s in event_shifts if s.date == "2026-11-19")
fri = next(s for s in event_shifts if s.date == "2026-11-20")
asked = [e.cleaner_id for e in roster.entries if e.status == "asked"]
script = {}
for cid in asked:  # one "only Thursday", one "too far", the rest a mix
    offered = {e.shift_id for e in roster.entries if e.cleaner_id == cid and e.status == "asked"}
    if thu.id in offered and fri.id in offered and "only Thursday" not in script.values():
        script[cid] = "only Thursday"
    elif "sorry, too far for me" not in script.values():
        script[cid] = "sorry, too far for me"
    else:
        script[cid] = "yes" if len(script) % 2 else "no, sorry"
for cid, text in script.items():
    print(f"\n<< {roster.cleaners[cid].name}: {text}")
    W.on_reply(cid, text)
    time.sleep(PAUSE)

far = next(c for c, t in script.items() if t.startswith("sorry, too far"))
W.on_reply(far, "about 30 minutes, I live in Libeň")
for e in list(roster.entries):
    if e.status == "confirmed":
        W.on_button(e.cleaner_id, "I agree")
        break
time.sleep(PAUSE)
thursday = next((e for e in roster.entries if e.shift_id == thu.id and e.status == "confirmed"), None)
if thursday:
    print(f"\n<< {roster.cleaners[thursday.cleaner_id].name}: sorry, I'm sick, can't do Thursday")
    W.on_cancel(thursday.cleaner_id, thu.id)
print("\n=== ROSTER ===\n" + roster.summary())
