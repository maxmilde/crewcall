"""Run the live agent on Telegram: python -m integrations.run_bot

Routes each incoming message:
- owner, a Menu command (/booked, /email, /reply, /post, /add) -> MENU (who's booked, last email, client reply, Facebook post, add cleaner)
- owner, a forwarded or long message -> a new client request (workflow.new_requests)
- client emails in the work Gmail inbox -> workflow.new_requests (integrations/gmail_inbox.py, Max's)
- owner, anything else -> owner_chat.handle, answer sent back
- known worker -> workflow.on_reply / on_button
- anyone else, or /start apply -> agent/applicants.py
In the background, reply_window moves on after REPLY_WAIT_MINUTES and reports full jobs.
"""
import os
from datetime import datetime

from agent import applicants, owner_chat, roster, workflow
from agent.describe import describe, label
from integrations import gmail_inbox, reply_window
from integrations import telegram_bot as bot
from shared.schemas import Request

EMAIL_MIN_CHARS = 300  # a pasted email is long; owner commands are short


def _is_email(msg: dict) -> bool:
    return "forward_origin" in msg or "forward_date" in msg or len(msg["text"]) >= EMAIL_MIN_CHARS


def _last_request() -> Request | None:
    return list(workflow.requests.values())[-1] if workflow.requests else None


def who_is_booked() -> str:
    """Per job: how many agreed out of how many needed, and their names. Nothing else."""
    if not roster.shifts:
        return "No jobs yet."
    lines = ["📋 Who's booked"]
    for shift in roster.shifts.values():
        names = [roster._name(e.cleaner_id) for e in roster._confirmed(shift.id)]
        needed = shift.headcount if shift.headcount is not None else "?"
        lines.append(f"{label(shift)}: {len(names)}/{needed}" + (f" ({', '.join(names)})" if names else ""))
    return "\n".join(lines)


def last_email() -> str:
    """What the agent read from the newest client email: jobs and open questions."""
    req = _last_request()
    if not req:
        return "No client emails yet."
    lines = [f"📧 Last email: {req.id}"]
    for s in (s for s in roster.shifts.values() if s.request_id == req.id):
        lines.append(f"- {describe(s)} · {s.headcount or '?'} people")
    if workflow.questions.get(req.id):
        lines += ["Still unclear:"] + [f"- {q.text}" for q in workflow.questions[req.id]]
    return "\n".join(lines)


def client_reply() -> str | None:
    req = _last_request()
    if not req:
        return "No client emails yet."
    workflow.client_reply(req.id)  # sends her the draft itself
    return None


def facebook_post() -> str | None:
    if not roster.shifts:
        return "No jobs yet."
    open_now = roster.open_shifts()
    if not open_now:
        return "All jobs are full, no post needed."
    workflow.recruit(open_now)  # sends her the draft itself
    return None


def add_cleaner() -> str:
    return "Send the name and area, e.g.:\nadd Jana Dvořáková, Žižkov"


# button label -> (command, what it does)
MENU = {
    "📋 Who's booked": ("booked", who_is_booked),
    "📧 Last email": ("email", last_email),
    "✉️ Client reply": ("reply", client_reply),
    "📣 Facebook post": ("post", facebook_post),
    "➕ Add cleaner": ("add", add_cleaner),
}
COMMANDS = {f"/{cmd}": fn for cmd, fn in MENU.values()} | {"/status": who_is_booked}


def on_owner(msg: dict) -> None:
    text = msg["text"].strip()
    action = MENU[text][1] if text in MENU else COMMANDS.get(text.split("@")[0].lower())
    if action:
        if answer := action():
            bot.notify_owner(answer)
        return
    if not _is_email(msg):
        bot.notify_owner(owner_chat.handle(text))
        return
    request = Request(id=f"request{len(workflow.requests) + 1}", raw_text=text,
                      received_at=datetime.now().isoformat(timespec="seconds"))
    bot.notify_owner("Got the email, reading it now...")
    workflow.new_requests([request])


def on_unknown(chat_id: str, text: str) -> None:
    if chat_id not in applicants.applicants:
        applicants.applicants[chat_id] = {}
        bot.send(chat_id, applicants.greeting())
        if text.startswith("/start"):
            return
    if not text.startswith("/start"):
        applicants.on_applicant(chat_id, text)


def main() -> None:
    if not bot.owner_chat_id():  # owner questions would go to a terminal nobody answers
        raise SystemExit("OWNER_CHAT_ID is missing in .env: the owner's phone can't be reached. Add it and restart.")
    bot.load_cleaners()
    name = os.getenv("TELEGRAM_BOT_NAME", "<bot>")
    print(f"Bot @{name} running. Owner chat: {bot.owner_chat_id() or '(terminal)'}")
    print(f"Applicant link: https://t.me/{name}?start=apply")
    for c in roster.cleaners.values():
        state = "linked" if c.telegram_chat_id else f"https://t.me/{name}?start={c.id}"
        print(f"  {c.id} {c.name}: {state}")
    bot.menu_texts = set(MENU)
    bot._api("setMyCommands", commands=[{"command": cmd, "description": label_}
                                        for label_, (cmd, _) in MENU.items()])
    gmail_inbox.watch(workflow.new_requests, lambda: set(workflow.requests))  # off until GMAIL_* are in .env
    reply_window.watch()
    bot.send(bot.owner_chat_id(), "Agent is online. Forward me a client email anytime, or open the Menu.",
             {"remove_keyboard": True})  # clears the old button keyboard; commands live in the Menu
    bot.listen(workflow.on_reply, workflow.on_button, on_owner, on_unknown)


if __name__ == "__main__":
    main()
