"""Scripted end-to-end run of the workflow on email 3 with 10 simulated workers.

Run: .venv/bin/python -m agent.simulate   (no Telegram or Apify needed)
"""
import time
from pathlib import Path

import agent.stand_ins as S
from agent import roster
from shared.schemas import Cleaner, Request

roster.STATE_FILE = Path("data/state_sim.json")
owner_answers = iter(["2", "2", "yes"])  # headcount for the two crew shifts, then go
S.ask_owner = lambda q: (S.notify_owner(q), print(f"     owner> {(a := next(owner_answers))}"))[1] or a

import agent.workflow as W  # noqa: E402  (after patching ask_owner)
W.ask_owner = S.ask_owner

areas = ["Vinohrady", "Žižkov", "Smíchov", "Karlín", "Holešovice", "Nusle", "Dejvice", "Libeň", "Vršovice", "Břevnov"]
names = ["Anna", "Petr", "Eva", "Jan", "Lucie", "Tomáš", "Marie", "Jakub", "Tereza", "Martin"]
roster.add_cleaners([Cleaner(f"c{i}", n, a, simulated=True) for i, (n, a) in enumerate(zip(names, areas))])

t = time.time()
shifts = W.start(Request(id="email3", raw_text=Path("data/requests/email3.txt").read_text(), received_at="2026-11-13T09:00:00"))
print(f"\n--- intake + approval: {time.time() - t:.0f}s"); t = time.time()
W.staff(shifts)
print(f"\n--- offers: {time.time() - t:.0f}s")

thu = next(s for s in shifts if s.date == "2026-11-19")
asked_thu = roster.pending(thu.id)
print(f"\nAsked for Thursday: {asked_thu}")
script = {asked_thu[0]: "Only Thursday", asked_thu[1]: "sorry, too far for me"}
for e in list(roster.entries):
    if e.status == "asked" and e.cleaner_id not in script:
        script[e.cleaner_id] = "no, sorry"
for cid, text in script.items():
    print(f"\n<< {roster.cleaners[cid].name}: {text}"); t = time.time()
    W.on_reply(cid, text)
    print(f"--- reply handled: {time.time() - t:.0f}s")
too_far = asked_thu[1]
print(f"\n<< {roster.cleaners[too_far].name}: about 30 minutes, I live in Libeň")
W.on_reply(too_far, "about 30 minutes, I live in Libeň")
W.on_button(asked_thu[0], "I agree")
print(f"\n<< {roster.cleaners[asked_thu[0]].name} cancels Thursday")
W.on_cancel(asked_thu[0], thu.id)
print("\n=== ROSTER ===\n" + roster.summary())
