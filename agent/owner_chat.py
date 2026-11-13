"""The owner talks to the agent in plain words. The model maps her message to one allowed action."""
import os
from datetime import datetime

from agent import roster, workflow
from agent.describe import describe
from shared.llm import chat_json
from shared.schemas import Cleaner, Request

PROMPT = """You are the staffing assistant of a small business owner. She wrote you a message.
Pick ONE action and return JSON:
{"action": "answer" | "set_headcount" | "remove_worker" | "add_worker" | "client_reply" | "send_reply" | "edit_reply" | "facebook_post" | "new_request" | "unknown",
 "shift_id": "id from the list" or null,
 "headcount": integer or null,
 "worker": "worker name exactly as in the roster" or null,
 "new_worker": {"name": str, "home_area": str or null, "email": str or null} or null,
 "answer": "short reply to her"}

- answer: she asks about the roster ("who's on Friday?", "what's still open?"). Answer from the roster only, in 1-3 short lines.
- set_headcount: she wants more or fewer people on a shift. headcount is the NEW total (current + change).
- remove_worker: she wants a worker taken off a shift. The agent then finds a replacement.
- add_worker: she gives details of a new person for her team; fill new_worker.
- new_request: she forwards or pastes a client's request for cleaning staff (an email or message from a client).
- client_reply: she wants the draft email to the client.
- send_reply: she approves a client draft ("send", "send it", "ok send"). shift_id may say which job.
- edit_reply: she wants changes to a client draft ("make it shorter", "mention parking"); put her instruction in "answer".
- facebook_post: she wants a job post for a shift (e.g. "post Friday on Facebook").
- unknown: anything else, or anything unclear. Say briefly what you can do.
Never invent shifts or people."""


def handle(text: str) -> str:
    """Returns the agent's reply to the owner. Actions are checked before anything changes."""
    shifts = "\n".join(
        f"- {describe(s, with_id=True)} | headcount {s.headcount}" for s in roster.shifts.values()
    )
    waiting = ", ".join(workflow.drafts) or "none"
    state = f"Shifts:\n{shifts}\n\nRoster:\n{roster.summary()}\n\nClient drafts waiting for her: {waiting}\n\nOwner's message: {text}"
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

    if action == "new_request":
        client = f"request{len(workflow.requests) + 1}"
        workflow.new_requests([Request(id=client, raw_text=text, received_at=datetime.now().isoformat(timespec="seconds"))])
        return "Done: that request is being staffed."

    new = data.get("new_worker") or {}
    if action == "add_worker" and isinstance(new, dict) and isinstance(new.get("name"), str) and new["name"].strip():
        if not (new.get("home_area") or "").strip():  # travel times need it
            return f"Which area does {new['name'].strip()} live in? Send it again with the area, e.g. \"add {new['name'].strip()}, Žižkov\"."
        worker_id = f"c{len(roster.cleaners) + 1:02d}"
        while worker_id in roster.cleaners:
            worker_id = f"c{int(worker_id[1:]) + 1:02d}"
        roster.add_cleaners([Cleaner(id=worker_id, name=new["name"].strip(), home_area=new.get("home_area") or "",
                                     email=new.get("email") or "")])
        roster.save()
        link = f"https://t.me/{os.getenv('TELEGRAM_BOT_NAME', '<bot>')}?start={worker_id}"
        return f"Added {new['name'].strip()} ({worker_id}, {new['home_area'].strip()}). Forward this link; once they tap it they get offers:\n{link}"

    if action == "facebook_post" and shift:
        workflow.recruit([shift])
        return "Draft is above: post it in your group. Replies come to me through the bot."

    if action in ("send_reply", "edit_reply"):
        pending = [r for r in workflow.drafts if not shift or r == shift.request_id]
        if not pending:
            return "There's no client draft waiting."
        request_id = pending[-1]
        if action == "send_reply":
            return workflow.send_reply(request_id)
        draft = workflow.revise_reply(request_id, str(data.get("answer") or text))
        return f"✉️ Updated draft:\n\n{draft}\n\nReply \"send\" to email it, or tell me what else to change."

    if action == "client_reply":
        request_id = shift.request_id if shift else next(iter(workflow.requests), None)
        if not request_id:
            return "There is no client request yet."
        workflow.client_reply(request_id)
        return "Draft sent to you above. Nothing goes to the client until you send it."

    return str(data.get("answer") or "I can tell you who is on each shift, change a headcount, remove someone, or draft the client reply.")
