"""The agent's workflow: a fixed sequence of steps with a few AI decision points.

Rules: the agent never contacts the client, never changes headcount, pay or shift
details, and only messages workers it selected. Anything for a new person or the
client goes through the owner.
"""
from concurrent.futures import ThreadPoolExecutor

from agent import events, roster
from agent.client_reply import draft_client_reply
from agent.describe import describe
from agent.documents import draft_assignment
from agent.intake import parse_request
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
questions: dict[str, list[OpenQuestion]] = {}  # request id -> open points for the client
minutes: dict[str, dict[str, int]] = {}    # shift id -> cleaner id -> travel minutes
waiting_for_travel: set[str] = set()       # cleaners we asked "how far would you travel?"


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
        notify_owner(f"Request from {req.id}:\n" + "\n".join(f"- {describe(s, True)}" for s in req_shifts))
    for s in shifts:
        if s.headcount is None:
            answer = ask_owner(f"How many people for {s.id} ({s.task_summary})?")
            s.headcount = int(answer) if answer.isdigit() and int(answer) > 0 else 1
            events.log("owner", f"Owner set {s.id} to {s.headcount} people")
    roster.save()
    if ask_owner("Start contacting workers? (yes/no)").lower() not in ("y", "yes"):
        return []
    events.log("owner", "Owner approved: contacting workers")
    return shifts


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
    pool = list(roster.cleaners.values())
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
def staff(shifts: list[Shift]) -> None:
    per_cleaner: dict[str, list[Shift]] = {}
    for s in shifts:
        still_needed = 2 * (s.headcount or 1) - len(roster.pending(s.id)) - len(roster._confirmed(s.id))
        for cid in _candidates(s):
            if still_needed <= 0:
                break
            other = roster.clash(cid, s) or next((p for p in per_cleaner.get(cid, []) if roster.overlaps(p, s)), None)
            if other:  # never double-book across clients
                events.log("skip", f"{roster._name(cid)} skipped for {s.id}: already on {other.id} at that time")
                continue
            per_cleaner.setdefault(cid, []).append(s)
            still_needed -= 1
    if not per_cleaner:
        return

    def offer(cid: str) -> None:
        cleaner = roster.cleaners[cid]
        nearest = min(minutes[s.id][cid] for s in per_cleaner[cid])
        text = compose(cleaner, per_cleaner[cid]) + f"\n(About {nearest} min from you by public transport.)"
        send(cleaner.telegram_chat_id or cid, text)
        roster.mark_asked(cid, [s.id for s in per_cleaner[cid]])
        events.log("offer", f"Offer to {cleaner.name} ({nearest} min away): {', '.join(s.id for s in per_cleaner[cid])}")

    with ThreadPoolExecutor(max_workers=8) as pool:  # offers are written in parallel
        list(pool.map(offer, per_cleaner))
    notify_owner(f"Sent offers to {len(per_cleaner)} workers: {', '.join(roster._name(c) for c in per_cleaner)}")
    roster.save()


# 4–5. A worker replied
def on_reply(cleaner_id: str, text: str) -> None:
    cleaner = roster.cleaners[cleaner_id]
    if cleaner_id in waiting_for_travel:  # answer to "how far would you travel?"
        waiting_for_travel.discard(cleaner_id)
        cleaner.max_travel_minutes, area = learn_travel(text)
        cleaner.home_area = area or cleaner.home_area
        notify_owner(f"Saved for {cleaner.name}: max {cleaner.max_travel_minutes or '?'} min, lives in {cleaner.home_area}")
        events.log("reply", f"Learned: {cleaner.name} travels max {cleaner.max_travel_minutes or '?'} min, lives in {cleaner.home_area}")
        roster.save()
        return
    offered = [roster.shifts[e.shift_id] for e in roster.entries if e.cleaner_id == cleaner_id and e.status == "asked"]
    if not offered:
        notify_owner(f"{cleaner.name} wrote: {text}")
        return
    reply = classify(text, offered, cleaner_id)
    events.log("reply", f"{cleaner.name}: \"{text}\" → {reply.label}" + (f" ({', '.join(reply.accepted_shift_ids)})" if reply.accepted_shift_ids else ""))
    for note in roster.apply(reply):
        print(f"     roster: {note}")
        if note.startswith("Remembered") or "standby" in note:
            events.log("reply", note)
    if reply.too_far:
        waiting_for_travel.add(cleaner_id)
        send(cleaner.telegram_chat_id or cleaner_id,
             "No problem. So I only ask you for jobs that suit you: how long a trip is fine for you, and which area do you live in?")
    if reply.label in ("question", "unclear"):
        notify_owner(f"{cleaner.name} replied: \"{text}\"" + (f"\nQuestion: {reply.question}" if reply.question else ""))
    confirmed = [roster.shifts[i] for i in reply.accepted_shift_ids if roster._entry(cleaner_id, i).status == "confirmed"]
    if confirmed:
        send_buttons(cleaner.telegram_chat_id or cleaner_id, draft_assignment(cleaner, confirmed), ["I agree"])
    roster.save()
    next_steps({s.id: s for s in offered}.values())


def on_button(cleaner_id: str, button: str) -> None:
    if button == "I agree":
        for e in roster.entries:
            if e.cleaner_id == cleaner_id and e.status == "confirmed" and not e.agreed_at:
                roster.agree(cleaner_id, e.shift_id)
        notify_owner(f"{roster._name(cleaner_id)} agreed to the assignment.")
        events.log("reply", f"{roster._name(cleaner_id)} tapped \"I agree\"")
        roster.save()


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
        notify_owner("Draft for your Facebook group (it links to our Telegram bot):\n\n" + draft_post(post))
        events.log("recruit", f"Facebook post drafted for {', '.join(s.id for s in post)}")


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
    notify_owner(f"{shift.id} is still open ({confirmed}/{shift.headcount}). Decision: {action}. {choice.get('reason', '')}")
    events.log("decision", f"{shift.id} open ({confirmed}/{shift.headcount}) → {action.replace('_', ' ')}: {choice.get('reason', '')}")
    if action == "tell_owner":
        notify_owner(f"I could not fill {shift.id}; please decide how to handle it.")
    return action


# 8. A confirmed worker cancels: standby first, then the next nearest
def on_cancel(cleaner_id: str, shift_id: str) -> None:
    roster.cancel(cleaner_id, shift_id)
    shift = roster.shifts[shift_id]
    notify_owner(f"{roster._name(cleaner_id)} cancelled {shift_id}. Re-staffing it now.")
    events.log("cancel", f"{roster._name(cleaner_id)} cancelled {shift_id}")
    waiting = roster.standby(shift_id)
    if waiting:
        roster.confirm(waiting[0], shift_id)
        cleaner = roster.cleaners[waiting[0]]
        send_buttons(cleaner.telegram_chat_id or cleaner.id,
                     "Good news: a place opened up and it's yours.\n\n" + draft_assignment(cleaner, [shift]), ["I agree"])
        notify_owner(f"{cleaner.name} moved from standby onto {shift_id}.")
        events.log("decision", f"{cleaner.name} moved from standby onto {shift_id}")
    else:
        staff([shift])
    roster.save()


# 9. Client reply: drafted for the owner, never sent by the agent
def client_reply(request_id: str) -> str:
    req_shifts = [s for s in roster.shifts.values() if s.request_id == request_id]
    draft = draft_client_reply(requests[request_id], req_shifts, questions.get(request_id, []))
    notify_owner("Draft reply to the client (review and send it yourself):\n\n" + draft)
    events.log("owner", f"Client reply for {request_id} drafted for the owner")
    return draft
