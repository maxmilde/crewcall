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
owner_answers = iter(["2", "2", "2", "yes", "yes"])  # headcounts the email leaves open, go, approve applicant


def owner(question):
    S.notify_owner(question)
    answer = next(owner_answers, "1")
    print(f"     owner> {answer}")
    return answer


S.ask_owner = owner
import agent.workflow as W  # noqa: E402  (after patching ask_owner)
W.ask_owner = owner
W.notify_owner, W.send, W.send_buttons = S.notify_owner, S.send, S.send_buttons  # terminal, not Telegram
W.travel_minutes, W.shortlist = S.travel_minutes, S.shortlist  # fake times: no Apify credits

roster.CSV_FILE = Path("data/cleaners_sim.csv")  # the simulation never overwrites the real contact list
roster.CSV_FILE.write_text(Path("data/sim_cleaners.csv").read_text(encoding="utf-8"), encoding="utf-8")
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


def beat(title):
    print(f"\n######## {title}")
    time.sleep(PAUSE)


def say(cid, text):
    print(f"\n<< {roster.cleaners[cid].name}: {text}")
    W.on_reply(cid, text)
    time.sleep(PAUSE)


beat("Replies come in")
asked = lambda sid: [e.cleaner_id for e in roster.entries if e.shift_id == sid and e.status == "asked"]
thu_people = asked(thu.id)
script = {}
if thu_people:
    script[thu_people[0]] = "only Thursday"
if len(thu_people) > 1:
    script[thu_people[1]] = "Thursday works for me"  # becomes standby
for cid in asked(fri.id):
    script.setdefault(cid, "no, sorry, I'm busy that week")
others = [e.cleaner_id for e in roster.entries if e.status == "asked" and e.cleaner_id not in script]
for i, cid in enumerate(dict.fromkeys(others)):
    script[cid] = "sorry, too far for me" if i == 0 else ("yes" if i % 2 else "no, sorry")
for cid, text in script.items():
    still_asked_fri = cid in asked(fri.id)  # keep Friday open for the recruiting part of the story
    say(cid, "no, sorry, I'm busy that week" if still_asked_fri and text == "yes" else text)

for cid in asked(fri.id):  # people asked for Friday in later rounds decline too
    say(cid, "sorry, can't that day")

beat("Learning limits and agreeing")
far = next((c for c, x in script.items() if x.startswith("sorry, too far")), None)
if far:
    say(far, "about 30 minutes, I live in Libeň")
first = next((e for e in roster.entries if e.shift_id == thu.id and e.status == "confirmed"), None)
if first:
    W.on_button(first.cleaner_id, "I agree")

beat("A cancellation")
if first:
    print(f"\n<< {roster.cleaners[first.cleaner_id].name}: sorry, I'm sick, can't do Thursday")
    W.on_cancel(first.cleaner_id, thu.id)

beat("Recruiting for Friday")
from agent import applicants, owner_chat  # noqa: E402
applicants.ask_owner = owner
print("\nOWNER: Friday is urgent, post it on Facebook\nAGENT:", owner_chat.handle("Friday is urgent, post it on Facebook"))
time.sleep(PAUSE)
print("\n<< (new person via the bot) hi, saw your post, I'm Lukas, I live in Karlín")
applicants.send("tg-new", applicants.greeting())
applicants.on_applicant("tg-new", "hi, saw your post, I'm Lukas, I live in Karlín")
print("\n<< Lukas: weekdays after 12, lukas.novak@example.com")
applicants.on_applicant("tg-new", "weekdays after 12, lukas.novak@example.com")

beat("Owner asks")
print("\nOWNER: who's on Friday?\nAGENT:", owner_chat.handle("who's on Friday?"))
print("\n=== ROSTER ===\n" + roster.summary())
