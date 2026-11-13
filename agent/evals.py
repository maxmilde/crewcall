"""Test cases for every AI step. Run after any prompt change:

    .venv/bin/python -m agent.evals            # all areas
    .venv/bin/python -m agent.evals classify   # one area
"""
import re
import sys
from concurrent.futures import ThreadPoolExecutor

from shared.schemas import Request, Shift

THU = Shift(id="thu", request_id="r", site_name="[venue]", date="2026-11-19", start="12:00", end="17:00",
            hours_confirmed=True, headcount=1, task_summary="on-site cleaner during an event")
FRI = Shift(id="fri", request_id="r", site_name="[venue]", date="2026-11-20", start="12:00", end="19:00",
            hours_confirmed=True, headcount=1, task_summary="on-site cleaner during an event")
TUE_WED = Shift(id="pre", request_id="r", site_name="[venue]", date_options=["2026-11-17", "2026-11-18"],
                headcount=2, task_summary="pre-event clean of a hall and two kitchens")


# --- classify: (reply, label, accepted ids, extra checks) ---------------------------------------
CLASSIFY = [
    ("ye sure", "yes", ["thu", "fri"], {}),
    ("yess both ok 👍", "yes", ["thu", "fri"], {}),
    ("ok", "yes", ["thu", "fri"], {}),
    ("only thrusday", "partial", ["thu"], {"no_constraints": True}),
    ("19th works, not the 20th", "partial", ["thu"], {}),
    ("Friday. Is there parking?", "partial", ["fri"], {"has_question": True}),
    ("can do friday but i have to leave at 6", ("question", "unclear"), [], {"has_question": True, "no_constraints": True}),
    ("thursday yes but I can only come at 14:00", "question", [], {"has_question": True}),
    ("no", "no", [], {}),
    ("nope too far for me", "no", [], {"too_far": True}),
    ("sorry, it's over an hour for me by tram", "no", [], {"too_far": True}),
    ("wrong number", "no", [], {}),
    ("stop messaging me", "no", [], {}),
    ("I'm sick this week, sorry", "no", [], {"no_constraints": True}),
    ("ano, oba dny", "yes", ["thu", "fri"], {}),
    ("jen v pátek", "partial", ["fri"], {}),
    ("ne, děkuji", "no", [], {}),
    ("Ja, Donnerstag passt", "partial", ["thu"], {}),
    ("what do i need to bring?", "question", [], {"has_question": True}),
    ("how much does it pay", "question", [], {"has_question": True}),
    ("maybe", "unclear", [], {}),
    ("I will tell you tomorrow", "unclear", [], {}),
    ("Thursday yes, Friday no. Also I never work Sundays", "partial", ["thu"], {"constraint": "sunday"}),
    ("no, I don't do evenings anymore", "no", [], {"constraint": "evening"}),
    ("yes both, and btw I never work weekends", "yes", ["thu", "fri"], {"constraint": "weekend"}),
    ("Friday works if I can bring my daughter", "question", [], {"has_question": True}),
]


def check_classify(case):
    from agent.replies import classify
    text, label, ids, extra = case
    r = classify(text, [THU, FRI])
    problems = []
    if r.label not in (label if isinstance(label, tuple) else (label,)):
        problems.append(f"label {r.label} != {label}")
    if sorted(r.accepted_shift_ids) != sorted(ids):
        problems.append(f"accepted {r.accepted_shift_ids} != {ids}")
    if extra.get("has_question") and not r.question:
        problems.append("no question passed on")
    if extra.get("no_constraints") and r.constraints:
        problems.append(f"one-off saved as rule {r.constraints}")
    if extra.get("too_far") and not r.too_far:
        problems.append("too_far not set")
    if "constraint" in extra and not any(extra["constraint"] in c.lower() for c in r.constraints):
        problems.append(f"rule '{extra['constraint']}' missing: {r.constraints}")
    return text, problems


# --- intake: (email, checks on shifts/questions) -------------------------------------------------
def _intake(text):
    from agent.intake import parse_request
    return parse_request(Request(id="t", raw_text=text, received_at="2026-11-13T09:00:00"))


INTAKE = [
    ("We need 3 cleaners every weekday 18:00-21:00 starting Tuesday 1 December at our office, Palackého 12, Prague 1.",
     lambda s, q: len(s) == 1 and s[0].headcount == 3 and s[0].recurrence == "weekdays" and s[0].date == "2026-12-01"
     and (s[0].start, s[0].end) == ("18:00", "21:00") and s[0].hours_confirmed and s[0].address is not None),
    ("Hello, on Monday 16/11 and Wednesday 18/11 we need 2 people each day, 9:00-13:00, to clean our new apartment block stairwells.",
     lambda s, q: len(s) == 2 and {x.date for x in s} == {"2026-11-16", "2026-11-18"} and all(x.headcount == 2 for x in s)),
    ("Could you send a few people this Saturday to clean up after our office party? Not sure about the time yet.",
     lambda s, q: len(s) == 1 and s[0].headcount is None and not s[0].hours_confirmed and s[0].date == "2026-11-14"
     and not any("how many" in x.text.lower() for x in q)),
    ("Please send us a quote for monthly window cleaning of our shop.",
     lambda s, q: all(x.start is None and x.date is None for x in s) and len(q) >= 1),
    ("Hi, 1 cleaner on Friday 20/11 from around 10 until lunchtime, office kitchen and toilets.",
     lambda s, q: len(s) == 1 and s[0].date == "2026-11-20" and not s[0].hours_confirmed and s[0].headcount == 1),
    (open("data/requests/email3.txt").read(),
     lambda s, q: len(s) >= 4 and sum(1 for x in s if x.date_options) == 2 and all(not x.hours_confirmed for x in s)
     and any(x.headcount is None for x in s)),
]


def check_intake(case):
    text, ok = case
    shifts, questions = _intake(text)
    good = ok(shifts, questions)
    detail = "; ".join(f"{x.date or x.date_options} {x.start}-{x.end} n={x.headcount} {x.recurrence} conf={x.hours_confirmed}" for x in shifts)
    return text[:60], [] if good else [f"got: {detail} | q={[x.text for x in questions]}"]


# --- compose and draft_post ----------------------------------------------------------------------
def check_compose(case):
    from agent.outreach import CLOSING, compose
    from agent.domain import settings
    from shared.schemas import Cleaner
    name, shifts = case
    text = compose(Cleaner("c", name, "Vinohrady"), shifts)
    problems = []
    body = text.replace(CLOSING, "")
    if len(body.split()) > 60:
        problems.append(f"{len(body.split())} words")
    if not text.endswith(CLOSING):
        problems.append("missing closing")
    if settings()["pay_text"].lower() not in text.lower():
        problems.append("pay text missing")
    if re.search(r"\d+\s?(€|eur|czk|kč)", text.lower()):
        problems.append("states an amount")
    for s in shifts:
        days = [s.date] if s.date else s.date_options
        for d in days:
            day = __import__("datetime").date.fromisoformat(d).strftime("%A")
            if day.lower()[:3] not in text.lower():
                problems.append(f"{day} missing")
    if name.split()[0] not in text:
        problems.append("name missing")
    return f"compose {name} {[s.id for s in shifts]}", problems


COMPOSE = [("Jana Nováková", [THU]), ("Petr", [THU, FRI]), ("Eva", [TUE_WED]), ("Tomáš", [TUE_WED, THU, FRI])]


def check_post(shifts):
    from agent.outreach import draft_post
    text = draft_post(shifts)
    problems = []
    if "good pay, bonuses, allowances and paid leave" not in text.lower():
        problems.append("her closing line changed")
    if re.search(r"\d+\s?(€|eur|czk|kč)", text.lower()):
        problems.append("states an amount")
    if len(text.split()) > 80:
        problems.append(f"{len(text.split())} words")
    return f"post {[s.id for s in shifts]}: {text[:70]}…", problems


POST = [[FRI], [TUE_WED], [THU, FRI]]


# --- decisions -----------------------------------------------------------------------------------
def check_decide(case):
    from agent.workflow import DECIDE_PROMPT
    from shared.llm import chat_json
    state, allowed = case
    action = chat_json(DECIDE_PROMPT, state, max_tokens=3000).get("action")
    return state.splitlines()[-1], [] if action in allowed else [f"chose {action}, expected {allowed}"]


DECIDE = [
    ("Shift: Friday 20 November 12:00–19:00\nNeeded: 1, confirmed: 0\nAsked and declined: 2\nWorkers not yet asked: 8", {"ask_more"}),
    ("Shift: Friday 20 November 12:00–19:00\nNeeded: 1, confirmed: 0\nAsked and declined: 10\nWorkers not yet asked: 0", {"facebook_post"}),
    ("Shift: Tuesday 17 November\nNeeded: 3, confirmed: 2\nAsked and declined: 9\nWorkers not yet asked: 0", {"facebook_post", "tell_owner"}),
    ("Shift: Thursday 19 November 12:00–17:00\nNeeded: 2, confirmed: 1\nAsked and declined: 3\nWorkers not yet asked: 5", {"ask_more"}),
]


# --- owner chat ----------------------------------------------------------------------------------
def check_owner(case):
    from agent import owner_chat
    from shared.llm import chat_json
    text, action, extra = case
    state = ("Shifts:\n- [thu] Thursday 19 November 12:00–17:00 at [venue] | headcount 1\n"
             "- [fri] Friday 20 November 12:00–19:00 at [venue] | headcount 1\n\n"
             "Roster:\n[OPEN] thu: confirmed 0/1, waiting for: Petr\n[FULL] fri: confirmed 1/1: Anna\n\n"
             f"Owner's message: {text}")
    data = chat_json(owner_chat.PROMPT, state, max_tokens=2000)
    problems = [] if data.get("action") == action else [f"action {data.get('action')} != {action}"]
    for key, value in extra.items():
        if str(data.get(key)).lower() != str(value).lower():
            problems.append(f"{key}={data.get(key)} != {value}")
    return text, problems


OWNER = [
    ("who's on friday?", "answer", {}),
    ("what's still open", "answer", {}),
    ("add 2 more people on thursday", "set_headcount", {"shift_id": "thu", "headcount": 3}),
    ("thursday needs one more", "set_headcount", {"shift_id": "thu", "headcount": 2}),
    ("take Anna off friday", "remove_worker", {"shift_id": "fri", "worker": "Anna"}),
    ("show me the email for the client", "client_reply", {}),
    ("cancel the whole job", "unknown", {}),
    ("what's the weather tomorrow", "unknown", {}),
]


# --- learn_travel and applicants -----------------------------------------------------------------
def check_travel(case):
    from agent.replies import learn_travel
    text, minutes, area = case
    m, a = learn_travel(text)
    problems = []
    if m not in minutes:
        problems.append(f"minutes {m} not in {minutes}")
    if area and (not a or area.lower() not in a.lower()):
        problems.append(f"area {a} != {area}")
    return text, problems


TRAVEL = [
    ("about 30 minutes, I live in Libeň", {30}, "Libeň"),
    ("an hour max, Smíchov", {60}, "Smíchov"),
    ("30-40 min, near Anděl", {30, 35, 40}, "Anděl"),
    ("I live in Karlín", {None}, "Karlín"),
]


def check_applicant(case):
    from agent.applicants import PROMPT
    from shared.llm import chat_json
    text, expected = case
    data = chat_json(PROMPT, f"Already known: {{}}\n\nTheir message: {text}", max_tokens=1000)
    problems = [f"{k}={data.get(k)}" for k, v in expected.items()
                if (v is None) != (data.get(k) is None) or (v and v.lower() not in str(data.get(k)).lower())]
    return text, problems


APPLICANTS = [
    ("Lukas here, Karlín, weekdays after 12, lukas.novak@example.com",
     {"name": "Lukas", "home_area": "Karlín", "availability": "weekday", "email": "lukas.novak@example.com"}),
    ("hi I saw your post, interested!", {"name": None, "home_area": None, "availability": None, "email": None}),
    ("Jana Dvořáková, mám čas o víkendech, bydlím na Žižkově", {"name": "Jana", "home_area": "Žižkov", "availability": "víkend", "email": None}),
]

AREAS = {
    "classify": (check_classify, CLASSIFY), "intake": (check_intake, INTAKE), "compose": (check_compose, COMPOSE),
    "post": (check_post, POST), "decide": (check_decide, DECIDE), "owner": (check_owner, OWNER),
    "travel": (check_travel, TRAVEL), "applicant": (check_applicant, APPLICANTS),
}


def main(names):
    total = passed = 0
    for name in names:
        check, cases = AREAS[name]
        with ThreadPoolExecutor(8) as pool:
            results = list(pool.map(check, cases))
        good = sum(1 for _, p in results if not p)
        total, passed = total + len(results), passed + good
        print(f"\n== {name}: {good}/{len(results)}")
        for label, problems in results:
            if problems:
                print(f"   MISS {label!r}: {'; '.join(problems)}")
    print(f"\nTOTAL {passed}/{total}")


if __name__ == "__main__":
    main(sys.argv[1:] or list(AREAS))
