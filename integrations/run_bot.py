"""Run the live agent on Telegram: python -m integrations.run_bot

Routes each incoming message:
- owner, /status (or "status", "summary") -> how many agreed per job, and who
- owner, a forwarded or long message -> a new client request (workflow.start, then staff)
- owner, anything else -> owner_chat.handle, answer sent back
- known worker -> workflow.on_reply / on_button
- anyone else, or /start apply -> agent/applicants.py
"""
import os
from datetime import datetime

from agent import applicants, owner_chat, roster, workflow
from agent.describe import label
from integrations import telegram_bot as bot
from shared.schemas import Request

EMAIL_MIN_CHARS = 300  # a pasted email is long; owner commands are short
STATUS_WORDS = ("/status", "status", "summary")


def _is_email(msg: dict) -> bool:
    return "forward_origin" in msg or "forward_date" in msg or len(msg["text"]) >= EMAIL_MIN_CHARS


def status() -> str:
    """Per job: how many agreed out of how many needed, and their names. Nothing else."""
    if not roster.shifts:
        return "No jobs yet."
    lines = ["📋 Status"]
    for shift in roster.shifts.values():
        names = [roster._name(e.cleaner_id) for e in roster._confirmed(shift.id)]
        needed = shift.headcount if shift.headcount is not None else "?"
        lines.append(f"{label(shift)}: {len(names)}/{needed}" + (f" ({', '.join(names)})" if names else ""))
    return "\n".join(lines)


def on_owner(msg: dict) -> None:
    text = msg["text"]
    if text.strip().lower() in STATUS_WORDS:
        bot.notify_owner(status())
        return
    if not _is_email(msg):
        bot.notify_owner(owner_chat.handle(text))
        return
    request = Request(id=f"request-{len(workflow.requests) + 1}", raw_text=text,
                      received_at=datetime.now().isoformat(timespec="seconds"))
    bot.notify_owner("Got the email, reading it now...")
    shifts = workflow.start([request])
    if shifts:
        workflow.staff(shifts)


def on_unknown(chat_id: str, text: str) -> None:
    if chat_id not in applicants.applicants:
        applicants.applicants[chat_id] = {}
        bot.send(chat_id, applicants.greeting())
        if text.startswith("/start"):
            return
    if not text.startswith("/start"):
        applicants.on_applicant(chat_id, text)


def main() -> None:
    bot.load_cleaners()
    name = os.getenv("TELEGRAM_BOT_NAME", "<bot>")
    print(f"Bot @{name} running. Owner chat: {bot.owner_chat_id() or '(terminal)'}")
    print(f"Applicant link: https://t.me/{name}?start=apply")
    for c in roster.cleaners.values():
        state = "linked" if c.telegram_chat_id else f"https://t.me/{name}?start={c.id}"
        print(f"  {c.id} {c.name}: {state}")
    bot._api("setMyCommands", commands=[{"command": "status", "description": "How many agreed per job, and who"}])
    bot.notify_owner("Agent is online. Forward me a client email, or send /status to see who agreed.")
    bot.listen(workflow.on_reply, workflow.on_button, on_owner, on_unknown)


if __name__ == "__main__":
    main()
