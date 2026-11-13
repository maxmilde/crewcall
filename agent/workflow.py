"""The agent's workflow: a fixed sequence of steps with a few AI decision points.

Rules: the agent never contacts the client, never changes headcount, pay or shift
details, and only messages workers it selected. Anything for a new person or the
client goes through the owner.
"""
from concurrent.futures import ThreadPoolExecutor

from agent import roster
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

request: Request | None = None
questions: list[OpenQuestion] = []
minutes: dict[str, dict[str, int]] = {}    # shift id -> cleaner id -> travel minutes
waiting_for_travel: set[str] = set()       # cleaners we asked "how far would you travel?"


# 1. Email in: parse, owner approves and sets headcount
def start(new_request: Request) -> list[Shift]:
    global request, questions
    request = new_request
    shifts, questions = parse_request(request)
    roster.add_shifts(shifts)
    notify_owner("New request. I read these shifts:\n" + "\n".join(f"- {describe(s, True)}" for s in shifts))
    for s in shifts:
        if s.headcount is None:
            answer = ask_owner(f"How many people for {s.id} ({s.task_summary})?")
            s.headcount = int(answer) if answer.isdigit() and int(answer) > 0 else 1
    if questions:
        notify_owner("Open points for the client:\n" + "\n".join(f"- {q.text}" for q in questions))
    if ask_owner("Start contacting workers? (yes/no)").lower() not in ("y", "yes"):
        return []
    return shifts


def _arrive_by(shift: Shift) -> str:
    day = shift.date or (shift.date_options[0] if shift.date_options else "")
    return f"{day}T{shift.start or '09:00'}"


def _candidates(shift: Shift) -> list[str]:
    """2. Nearest first, skipping people already asked or out of their travel range."""
    pool = list(roster.cleaners.values())
    if shift.id not in minutes:
        minutes[shift.id] = travel_minutes(pool, shift.address or shift.site_name or "", _arrive_by(shift))
    times = minutes[shift.id]
    asked = roster.asked_before(shift.id)
    ordered = shortlist(shift, pool, times)
    return [
        c.id for c in ordered
        if c.id not in asked and (c.max_travel_minutes is None or times.get(c.id, 0) <= c.max_travel_minutes)
    ]


# 2–3. Ask 2N nearest per shift; one message per worker covering all their shifts
def staff(shifts: list[Shift]) -> None:
    per_cleaner: dict[str, list[Shift]] = {}
    for s in shifts:
        still_needed = 2 * (s.headcount or 1) - len(roster.pending(s.id)) - len(roster._confirmed(s.id))
        for cid in _candidates(s)[: max(still_needed, 0)]:
            per_cleaner.setdefault(cid, []).append(s)
    if not per_cleaner:
        return

    def offer(cid: str) -> None:
        cleaner = roster.cleaners[cid]
        nearest = min(minutes[s.id][cid] for s in per_cleaner[cid])
        text = compose(cleaner, per_cleaner[cid]) + f"\n(About {nearest} min from you by public transport.)"
        send(cleaner.telegram_chat_id or cid, text)
        roster.mark_asked(cid, [s.id for s in per_cleaner[cid]])

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
        roster.save()
        return
    offered = [roster.shifts[e.shift_id] for e in roster.entries if e.cleaner_id == cleaner_id and e.status == "asked"]
    if not offered:
        notify_owner(f"{cleaner.name} wrote: {text}")
        return
    reply = classify(text, offered, cleaner_id)
    for note in roster.apply(reply):
        print(f"     roster: {note}")
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
    if action == "tell_owner":
        notify_owner(f"I could not fill {shift.id}; please decide how to handle it.")
    return action


# 8. A confirmed worker cancels: standby first, then the next nearest
def on_cancel(cleaner_id: str, shift_id: str) -> None:
    roster.cancel(cleaner_id, shift_id)
    shift = roster.shifts[shift_id]
    notify_owner(f"{roster._name(cleaner_id)} cancelled {shift_id}. Re-staffing it now.")
    waiting = roster.standby(shift_id)
    if waiting:
        roster.confirm(waiting[0], shift_id)
        cleaner = roster.cleaners[waiting[0]]
        send_buttons(cleaner.telegram_chat_id or cleaner.id,
                     "Good news: a place opened up and it's yours.\n\n" + draft_assignment(cleaner, [shift]), ["I agree"])
        notify_owner(f"{cleaner.name} moved from standby onto {shift_id}.")
    else:
        staff([shift])
    roster.save()


# 9. Client reply: drafted for the owner, never sent by the agent
def client_reply() -> str:
    draft = draft_client_reply(request, list(roster.shifts.values()), questions)
    notify_owner("Draft reply to the client (review and send it yourself):\n\n" + draft)
    return draft
