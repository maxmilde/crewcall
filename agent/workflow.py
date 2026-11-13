"""The agent's workflow: a fixed sequence of steps with a few AI decision points.

Rules: the agent never contacts the client, never changes headcount, pay or shift
details, and only messages workers it selected. Anything for a new person or the
client goes through the owner.
"""
import threading
from concurrent.futures import ThreadPoolExecutor

from agent import events, job_status, roster
from agent.client_reply import draft_client_reply
from agent.describe import describe, label, where
from agent.documents import draft_assignment
from agent.intake import client_names, parse_request
from agent.outreach import compose, draft_post
from agent.replies import classify, learn_travel
from shared.llm import chat_json
from shared.schemas import OpenQuestion, Request, Shift

try:  # real integrations once they exist, terminal stand-ins until then
    from integrations.telegram_bot import ask_owner, notify_owner, send, send_buttons
except ImportError:
    from agent.stand_ins import ask_owner, notify_owner, send, send_buttons
try:
    from integrations.apify_travel import travel_minutes
    from agent.matching import shortlist
except ImportError:
    from agent.stand_ins import shortlist, travel_minutes

requests: dict[str, Request] = {}
client_contacts: dict[str, tuple[str, str]] = {}  # request id -> (client email, original subject), from the inbox
drafts: dict[str, str] = {}                       # request id -> client reply waiting for the owner's "send"
questions: dict[str, list[OpenQuestion]] = {}  # request id -> open points for the client
minutes: dict[str, dict[str, int]] = {}    # shift id -> cleaner id -> travel minutes
waiting_for_travel: set[str] = set()       # cleaners we asked "how far would you travel?"
lock = threading.RLock()                   # replies arrive from several threads (bot, simulated workers)


def _locked(fn):
    def wrapper(*args, **kwargs):
        with lock:
            result = fn(*args, **kwargs)
            job_status.refresh()  # the owner's job cards follow every change
            return result
    wrapper.__name__, wrapper.__doc__ = fn.__name__, fn.__doc__
    return wrapper


def _send(cleaner_id: str, text: str, buttons: list[str] | None = None) -> None:
    """Send to the worker's phone. Simulated workers (agent.simulate only) get nothing."""
    cleaner = roster.cleaners[cleaner_id]
    if not cleaner.simulated:
        if not cleaner.telegram_chat_id:
            events.log("skip", f"{cleaner.name} has no Telegram chat yet (needs /start)")
            return
        if buttons:
            send_buttons(cleaner.telegram_chat_id, text, buttons)
        else:
            send(cleaner.telegram_chat_id, text)


# 1. Emails in: read them all at once, owner sets headcounts and approves
def start(new_requests: list[Request]) -> list[Shift]:
    with ThreadPoolExecutor(max_workers=4) as pool:
        parsed = list(pool.map(parse_request, new_requests))
    shifts = []
    for req, (req_shifts, req_questions) in zip(new_requests, parsed):
        requests[req.id], questions[req.id] = req, req_questions
        roster.add_shifts(req_shifts)
        shifts += req_shifts
        events.log("request", f"Email from {req.id}: {len(req_shifts)} shifts read")
        notify_owner(_request_summary(req, req_shifts))
    for s in shifts:
        if s.headcount is None:
            answer = ask_owner(f"❓ How many people for {label(s)} ({s.task_summary})?")
            s.headcount = int(answer) if answer.isdigit() and int(answer) > 0 else 1
            events.log("owner", f"Owner set {s.id} to {s.headcount} people")
    roster.save()
    if ask_owner("Shall I start asking people? (yes/no)").lower() not in ("y", "yes"):
        return []
    events.log("owner", "Owner approved: contacting workers")
    return shifts


def _hours(s: Shift) -> str:
    if not (s.start and s.end):
        return "hours tbc"
    return f"{s.start}–{s.end}" + ("" if s.hours_confirmed else " (approx.)")


def _request_summary(req: Request, req_shifts: list[Shift]) -> str:
    """What the owner sees first: who, where, which shifts, what is still open."""
    places = list(dict.fromkeys(where(s) for s in req_shifts))
    lines = [f"📩 New request: {client_names.get(req.id, req.id)}", f"📍 {' / '.join(places) or 'location tbc'}"]
    for s in req_shifts:
        day = label(s).split(f" {s.request_id}")[0]
        people = f"{s.headcount} {'person' if s.headcount == 1 else 'people'}" if s.headcount else "how many people?"
        lines.append(f"• {day} {_hours(s)}: {s.task_summary}, {people}")
    known = sum(s.headcount or 0 for s in req_shifts)
    unknown = sum(1 for s in req_shifts if not s.headcount)
    lines.append(f"👥 {known} people" + (f" + {unknown} {'shift' if unknown == 1 else 'shifts'} where you decide the headcount" if unknown else ""))
    open_points = questions.get(req.id, [])
    if open_points:
        lines.append("❓ Still open for the client:\n" + "\n".join(f"  – {q.text}" for q in open_points))
    return "\n".join(lines)


def new_requests(new: list[Request]) -> None:
    """Entry point for the inbox and forwarded emails: read, owner approves, ask people."""
    shifts = start(new)
    if shifts:
        staff(shifts)


def _arrive_by(shift: Shift) -> str:
    day = shift.date or (shift.date_options[0] if shift.date_options else "")
    return f"{day}T{shift.start or '09:00'}"


RULES_PROMPT = """A shift is offered. Some workers have personal rules about when or where they work.
Check each rule against the shift's weekday, start and end time and place.
Return {"excluded": ["worker id", ...]}: the ids whose rule is broken by this shift
(e.g. "nothing after 18:00" is broken by a shift ending at 19:00; "never weekends" by a Saturday).
Keep anyone whose rule is not broken or cannot be judged."""
_excluded: dict[tuple, bool] = {}  # (shift id, worker id, rules) -> excluded


def _rules_exclude(shift: Shift, cleaner_ids: list[str]) -> set[str]:
    """Learned rules like "never weekends": one model call per shift for everyone with rules."""
    todo = [c for c in cleaner_ids if roster.cleaners[c].constraints
            and (shift.id, c, tuple(roster.cleaners[c].constraints)) not in _excluded]
    if todo:
        lines = "\n".join(f"- {c}: {'; '.join(roster.cleaners[c].constraints)}" for c in todo)
        try:
            out = set(chat_json(RULES_PROMPT, f"Shift: {describe(shift)}\nWorkers:\n{lines}", max_tokens=1000).get("excluded") or [])
        except ValueError:
            out = set()
        for c in todo:
            _excluded[(shift.id, c, tuple(roster.cleaners[c].constraints))] = c in out
            if c in out:
                events.log("skip", f"{roster._name(c)} skipped for {shift.id}: {'; '.join(roster.cleaners[c].constraints)}")
    return {c for c in cleaner_ids if roster.cleaners[c].constraints
            and _excluded.get((shift.id, c, tuple(roster.cleaners[c].constraints)))}


def _candidates(shift: Shift) -> list[str]:
    """2. Nearest first, skipping people already asked, out of their travel range, or ruled out by their rules."""
    pool = [c for c in roster.cleaners.values() if c.simulated or c.telegram_chat_id]  # real phones need /start first
    if shift.id not in minutes:
        minutes[shift.id] = travel_minutes(pool, shift.address or shift.site_name or "", _arrive_by(shift))
    times = minutes[shift.id]
    asked = roster.asked_before(shift.id)
    ordered = shortlist(shift, pool, times)
    ids = [
        c.id for c in ordered
        if c.id not in asked and (c.max_travel_minutes is None or times.get(c.id, 0) <= c.max_travel_minutes)
    ]
    ruled_out = _rules_exclude(shift, ids)
    return [c for c in ids if c not in ruled_out]


# 2–3. Ask 2N nearest per shift; one message per worker covering all their shifts
@_locked
def staff(shifts: list[Shift]) -> None:
    per_cleaner: dict[str, list[Shift]] = {}
    skipped: list[str] = []
    for s in shifts:
        still_needed = 2 * (s.headcount or 1) - len(roster.pending(s.id)) - len(roster._confirmed(s.id))
        for cid in _candidates(s):
            if still_needed <= 0:
                break
            other = roster.clash(cid, s) or next((p for p in per_cleaner.get(cid, []) if roster.overlaps(p, s)), None)
            if other:  # never double-book across clients
                events.log("skip", f"{roster._name(cid)} skipped for {s.id}: already on {other.id} at that time")
                skipped.append(f"{roster._name(cid)} (busy: {label(other)})")
                continue
            per_cleaner.setdefault(cid, []).append(s)
            still_needed -= 1
    if not per_cleaner:
        if skipped:
            notify_owner("⏭ Nobody free to ask. Skipped: " + ", ".join(dict.fromkeys(skipped)))
        return

    def offer(cid: str) -> None:
        cleaner = roster.cleaners[cid]
        nearest = min(minutes[s.id][cid] for s in per_cleaner[cid])
        text = compose(cleaner, per_cleaner[cid]) + f"\n(About {nearest} min from you by public transport.)"
        roster.mark_asked(cid, [s.id for s in per_cleaner[cid]])
        _send(cid, text)
        events.log("offer", f"Offer to {cleaner.name} ({nearest} min away): {', '.join(s.id for s in per_cleaner[cid])}")

    with ThreadPoolExecutor(max_workers=8) as pool:  # offers are written in parallel
        list(pool.map(offer, per_cleaner))
    asked = ", ".join(f"{roster._name(c)} ({min(minutes[s.id][c] for s in per_cleaner[c])} min)" for c in per_cleaner)
    skipped = [s for s in skipped if s.split(" (")[0] not in {roster._name(c) for c in per_cleaner}]
    notify_owner(f"📤 Asked {len(per_cleaner)} {'person' if len(per_cleaner) == 1 else 'people'}, nearest first: {asked}"
                 + ("\n⏭ Skipped: " + ", ".join(dict.fromkeys(skipped)) if skipped else ""))
    roster.save()


# 4–5. A worker replied
@_locked
def on_reply(cleaner_id: str, text: str) -> None:
    cleaner = roster.cleaners[cleaner_id]
    if cleaner_id in waiting_for_travel:  # answer to "how far would you travel?"
        waiting_for_travel.discard(cleaner_id)
        cleaner.max_travel_minutes, area = learn_travel(text)
        cleaner.home_area = area or cleaner.home_area
        notify_owner(f"🧠 Saved for {cleaner.name}: max {cleaner.max_travel_minutes or '?'} min, lives in {cleaner.home_area}. Next time I'll only ask for jobs within that.")
        events.log("reply", f"Learned: {cleaner.name} travels max {cleaner.max_travel_minutes or '?'} min, lives in {cleaner.home_area}")
        roster.save()
        return
    offered = [roster.shifts[e.shift_id] for e in roster.entries if e.cleaner_id == cleaner_id and e.status == "asked"]
    if not offered:
        booked = [roster.shifts[e.shift_id] for e in roster.entries if e.cleaner_id == cleaner_id and e.status == "confirmed"]
        dropped = _cancelled(text, booked) if booked else []
        for shift in dropped:
            on_cancel(cleaner_id, shift.id)
        if dropped:
            _send(cleaner_id, "Thanks for letting us know. I'll find someone else.")
        else:
            notify_owner(f"❓ {cleaner.name} wrote: \"{text}\"")  # not an answer to anything: the owner decides
        return
    reply = classify(text, offered, cleaner_id)
    events.log("reply", f"{cleaner.name}: \"{text}\" → {reply.label}" + (f" ({', '.join(reply.accepted_shift_ids)})" if reply.accepted_shift_ids else ""))
    for note in roster.apply(reply):
        print(f"     roster: {note}")
        if note.startswith("Remembered") or "standby" in note:
            events.log("reply", note)
    if reply.too_far:
        waiting_for_travel.add(cleaner_id)
        _send(cleaner_id, "No problem. So I only ask you for jobs that suit you: how long a trip is fine for you, and which area do you live in?")
    _tell_owner_about(cleaner, text, reply)
    confirmed = [roster.shifts[i] for i in reply.accepted_shift_ids if roster._entry(cleaner_id, i).status == "confirmed"]
    if confirmed:
        _send(cleaner_id, draft_assignment(cleaner, confirmed), ["I agree"])
    roster.save()
    next_steps({s.id: s for s in offered}.values())
    _check_complete(reply.accepted_shift_ids)


def _tell_owner_about(cleaner, text: str, reply) -> None:
    """One short line per reply, so the owner sees what the agent understood."""
    taken = [label(roster.shifts[i]) for i in reply.accepted_shift_ids if roster._entry(cleaner.id, i).status == "confirmed"]
    standby = [label(roster.shifts[i]) for i in reply.accepted_shift_ids if roster._entry(cleaner.id, i).status == "standby"]
    line = f"💬 {cleaner.name}: \"{text}\""
    if taken:
        line += f"\n✅ Booked: {', '.join(taken)}"
    if standby:
        line += f"\n⏸ Standby (already full): {', '.join(standby)}"
    if reply.label == "no":
        line += "\n❌ Declined" + (", too far. Asking their travel limit." if reply.too_far else ".")
    if reply.label in ("question", "unclear"):
        line += f"\n❓ Needs you: {reply.question or 'unclear answer'}"
    if reply.constraints:
        line += f"\n🧠 Remembered: {'; '.join(reply.constraints)}"
    notify_owner(line)


@_locked
def contract_signed(cleaner_id: str) -> None:
    """The worker emailed back their signed work contract."""
    cleaner = roster.cleaners[cleaner_id]
    cleaner.contract_status = "signed"
    roster.save()
    events.log("recruit", f"{cleaner.name} returned the signed contract")
    notify_owner(f"✍️ {cleaner.name} returned the signed contract. They're ready for their first shift.")


CANCEL_PROMPT = """A worker who is booked on the shifts below sent a message.
Return {"cancels": ["shift id", ...]}: the shifts they say they can no longer do
(illness, emergency, "can't come", "have to cancel"). Empty if they don't cancel anything.
If they cancel without saying which, and only one shift is listed, that one."""


def _cancelled(text: str, booked: list[Shift]) -> list[Shift]:
    listing = "\n".join(f"- [{s.id}] {describe(s)}" for s in booked)
    try:
        ids = chat_json(CANCEL_PROMPT, f"Booked shifts:\n{listing}\n\nMessage: {text}", max_tokens=500).get("cancels") or []
    except ValueError:
        return []
    return [s for s in booked if s.id in ids]


@_locked
def on_button(cleaner_id: str, button: str) -> None:
    if button != "I agree":
        return
    agreed = []
    for e in roster.entries:
        if e.cleaner_id == cleaner_id and e.status == "confirmed" and not e.agreed_at:
            roster.agree(cleaner_id, e.shift_id)
            agreed.append(label(roster.shifts[e.shift_id]))
    if agreed:  # the worker always sees that the tap worked
        _send(cleaner_id, "✅ Thanks, you're booked: " + ", ".join(agreed) + ". See you there!")
        notify_owner(f"✍️ {roster._name(cleaner_id)} confirmed the assignment.")
        events.log("reply", f"{roster._name(cleaner_id)} tapped \"I agree\"")
        roster.save()
    else:
        _send(cleaner_id, "Thanks! There's nothing new to confirm right now.")


DECIDE_PROMPT = """You coordinate staffing for a small business. A shift is still missing people and
everyone asked so far has answered. Choose the next move.
Return {"action": "ask_more" | "facebook_post" | "tell_owner", "reason": "one short sentence"}.
- ask_more: only if there are workers not yet asked.
- facebook_post: when the own pool is used up or most declined; the owner posts it herself.
- tell_owner: when the shift cannot sensibly be filled (e.g. it starts too soon)."""


# 6. Decision point: everyone answered, shift still open
def next_steps(shifts) -> None:
    """Decide for each finished-but-open shift, then act once for all of them."""
    actions = {s.id: decide(s) for s in shifts if not roster.is_full(s.id) and not roster.pending(s.id)}
    more = [roster.shifts[i] for i, a in actions.items() if a == "ask_more"]
    post = [roster.shifts[i] for i, a in actions.items() if a == "facebook_post"]
    if more:
        staff(more)  # one message per worker, even when several shifts reopen
    if post:
        recruit(post)
    job_status.refresh()


def recruit(shifts: list[Shift]) -> str:
    """7. Draft the Facebook post for the owner; applicants answer through the bot."""
    post = draft_post(shifts)
    why = "; ".join(f"{label(s)} has {len(roster._confirmed(s.id))} of {s.headcount or '?'}" for s in shifts)
    notify_owner(f"📣 {why}, and nobody else in your team is free.\nDraft for your Facebook group (applicants reach me through the bot):\n\n" + post)
    events.log("recruit", f"Facebook post drafted for {', '.join(s.id for s in shifts)}")
    return post


def decide(shift: Shift) -> str:
    left = len(_candidates(shift))
    confirmed = len(roster._confirmed(shift.id))
    state = (f"Shift: {describe(shift)}\nNeeded: {shift.headcount}, confirmed: {confirmed}\n"
             f"Asked and declined: {len(roster.asked_before(shift.id)) - confirmed}\nWorkers not yet asked: {left}")
    try:
        choice = chat_json(DECIDE_PROMPT, state, max_tokens=3000)
    except ValueError:
        choice = {"action": "ask_more" if left else "facebook_post", "reason": "(fallback rule)"}
    action = choice.get("action")
    if action == "ask_more" and left == 0:
        action = "facebook_post"  # the model may not ask people who do not exist
    if action not in ("ask_more", "facebook_post"):
        action = "tell_owner"
    words = {"ask_more": "asking more people", "facebook_post": "nobody left, drafting a Facebook post", "tell_owner": "needs you"}
    notify_owner(f"🟠 {label(shift)} still needs {shift.headcount - confirmed}: {words[action]}.")
    events.log("decision", f"{shift.id} open ({confirmed}/{shift.headcount}) → {action.replace('_', ' ')}: {choice.get('reason', '')}")
    if action == "tell_owner":
        notify_owner(f"⚠️ I can't fill {label(shift)} sensibly. How do you want to handle it?")
    return action


# 8. A confirmed worker cancels: standby first, then the next nearest
@_locked
def on_cancel(cleaner_id: str, shift_id: str) -> None:
    roster.cancel(cleaner_id, shift_id)
    shift = roster.shifts[shift_id]
    notify_owner(f"⚠️ {roster._name(cleaner_id)} cancelled {label(shift)}. Re-staffing it now.")
    events.log("cancel", f"{roster._name(cleaner_id)} cancelled {shift_id}")
    waiting = roster.standby(shift_id)
    if waiting:
        roster.confirm(waiting[0], shift_id)
        cleaner = roster.cleaners[waiting[0]]
        _send(cleaner.id, "Good news: a place opened up and it's yours.\n\n" + draft_assignment(cleaner, [shift]), ["I agree"])
        notify_owner(f"✅ {cleaner.name} moved in from standby for {label(shift)}.")
        _check_complete([shift_id])
        events.log("decision", f"{cleaner.name} moved from standby onto {shift_id}")
    else:
        staff([shift])
    roster.save()


# 9. Client reply: drafted for the owner, never sent by the agent
def client_reply(request_id: str, complete: bool = False) -> str:
    """Draft the reply to the client and show it to the owner; it is sent only on her "send"."""
    req_shifts = [s for s in roster.shifts.values() if s.request_id == request_id]
    draft = draft_client_reply(requests[request_id], req_shifts, questions.get(request_id, []))
    drafts[request_id] = draft
    who = client_names.get(request_id, request_id)
    head = f"✅ Everyone's booked for {who}. " if complete else ""
    how = ("Reply \"send\" to email it, or tell me what to change." if request_id in client_contacts
           else "This request came through Telegram, so I don't have the client's email: copy it and send it yourself.")
    notify_owner(f"{head}✉️ Draft reply to {who}:\n\n{draft}\n\n{how}")
    events.log("owner", f"Client reply for {request_id} drafted for the owner")
    return draft


REVISE_PROMPT = """Rewrite this email draft following the owner's instruction. Keep everything else the same.
Return {"draft": "Subject: ...\\n\\n<body>"}."""


def revise_reply(request_id: str, instruction: str) -> str:
    try:
        new = chat_json(REVISE_PROMPT, f"Draft:\n{drafts[request_id]}\n\nInstruction: {instruction}", max_tokens=2000).get("draft")
    except ValueError:
        new = None
    if isinstance(new, str) and new.strip():
        drafts[request_id] = new.strip()
    return drafts[request_id]


def send_reply(request_id: str) -> str:
    """The owner said "send": email the approved draft to the client from the work inbox."""
    from integrations.email_sender import send_email
    to, subject = client_contacts.get(request_id, ("", ""))
    if not to:
        return "I don't have this client's email address, so please send it yourself."
    draft = drafts.pop(request_id)
    lines = draft.split("\n")
    body = "\n".join(lines[2:]) if lines and lines[0].lower().startswith("subject:") else draft
    send_email(to, subject if subject.lower().startswith("re:") else f"Re: {subject}", body.strip())
    events.log("owner", f"Client reply for {request_id} sent to {to}")
    return f"📨 Sent to {to}."


def _check_complete(shift_ids) -> None:
    """When every shift of a request is full, draft the client reply once."""
    for request_id in {roster.shifts[i].request_id for i in shift_ids if i in roster.shifts}:
        mine = [s for s in roster.shifts.values() if s.request_id == request_id]
        if request_id in requests and request_id not in drafts and mine and all(roster.is_full(s.id) for s in mine):
            client_reply(request_id, complete=True)
