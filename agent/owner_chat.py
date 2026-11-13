"""The owner talks to the agent in plain words. The model maps her message to one allowed action."""
from agent import roster, workflow
from agent.describe import describe
from shared.llm import chat_json

PROMPT = """You are the staffing assistant of a small business owner. She wrote you a message.
Pick ONE action and return JSON:
{"action": "answer" | "set_headcount" | "remove_worker" | "client_reply" | "unknown",
 "shift_id": "id from the list" or null,
 "headcount": integer or null,
 "worker": "worker name exactly as in the roster" or null,
 "answer": "short reply to her"}

- answer: she asks about the roster ("who's on Friday?", "what's still open?"). Answer from the roster only, in 1-3 short lines.
- set_headcount: she wants more or fewer people on a shift. headcount is the NEW total (current + change).
- remove_worker: she wants a worker taken off a shift. The agent then finds a replacement.
- client_reply: she wants the draft email to the client.
- unknown: anything else, or anything unclear. Say briefly what you can do.
Never invent shifts or people."""


def handle(text: str) -> str:
    """Returns the agent's reply to the owner. Actions are checked before anything changes."""
    shifts = "\n".join(
        f"- {describe(s, with_id=True)} | headcount {s.headcount}" for s in roster.shifts.values()
    )
    state = f"Shifts:\n{shifts}\n\nRoster:\n{roster.summary()}\n\nOwner's message: {text}"
    try:
        data = chat_json(PROMPT, state, max_tokens=2000)
    except ValueError:
        return "Sorry, I didn't get that. Ask me who is on a shift, change a headcount, or remove someone."

    action, shift_id = data.get("action"), data.get("shift_id")
    shift = roster.shifts.get(shift_id) if shift_id else None

    if action == "set_headcount" and shift and isinstance(data.get("headcount"), int) and 0 < data["headcount"] <= 30:
        old, shift.headcount = shift.headcount, data["headcount"]
        roster.save()
        if not roster.is_full(shift.id):
            workflow.staff([shift])
        return f"{shift.id}: headcount {old} → {shift.headcount}." + ("" if roster.is_full(shift.id) else " Asking more people now.")

    if action == "remove_worker" and shift:
        worker = next((c for c in roster.cleaners.values() if c.name.lower() == str(data.get("worker", "")).lower()), None)
        entry = worker and roster._entry(worker.id, shift.id)
        if entry and entry.status == "confirmed":
            workflow.on_cancel(worker.id, shift.id)
            return f"Took {worker.name} off {shift.id} and started finding a replacement."
        return "That person isn't confirmed on that shift."

    if action == "client_reply":
        request_id = shift.request_id if shift else next(iter(workflow.requests), None)
        if not request_id:
            return "There is no client request yet."
        workflow.client_reply(request_id)
        return "Draft sent to you above. Nothing goes to the client until you send it."

    return str(data.get("answer") or "I can tell you who is on each shift, change a headcount, remove someone, or draft the client reply.")
