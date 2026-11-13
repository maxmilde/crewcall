"""New people who answer the Facebook post by messaging the Telegram bot.

The agent collects name, area, availability and email; the owner decides who joins.
Approved people get the work contract by email and offers for the open shifts.
"""
import uuid

from agent import events, roster
from agent.documents import draft_contract
from agent.domain import settings
from agent.outreach import compose
from shared.llm import chat_json
from shared.schemas import Cleaner

try:
    from integrations.telegram_bot import ask_owner, send
except ImportError:
    from agent.stand_ins import ask_owner, send
try:
    from integrations.email import send_email
except ImportError:
    from agent.stand_ins import send_email

FIELDS = ("name", "home_area", "availability", "email")
applicants: dict[str, dict] = {}  # chat id -> what we know so far

PROMPT = """A person answered a job post by message. Extract what they told us, merged with what we already know.
Return {"name": str or null, "home_area": "district or street" or null,
        "availability": "days/times they can work, short" or null, "email": str or null}.
Keep known values unless the person corrects them. Never invent values."""


def greeting() -> str:
    return (f"Hi! Thanks for your interest in working as a {settings()['worker']}. "
            "Please tell me your name, which area you live in, when you can work, and your email address.")


def on_applicant(chat_id: str, text: str) -> None:
    known = applicants.setdefault(chat_id, {})
    data = chat_json(PROMPT, f"Already known: {known}\n\nTheir message: {text}", max_tokens=1000)
    known.update({k: v.strip() for k, v in data.items() if k in FIELDS and isinstance(v, str) and v.strip()})

    missing = [f for f in FIELDS if f not in known]
    if missing:
        send(chat_id, "Thanks! I still need: " + ", ".join(m.replace("home_area", "your area") for m in missing) + ".")
        return

    send(chat_id, "Thank you! The owner will get back to you shortly.")
    summary = "\n".join(f"{k}: {known[k]}" for k in FIELDS)
    if ask_owner(f"🙋 New applicant from your Facebook post:\n{summary}\nAdd them to your team? (yes/no)").lower() not in ("y", "yes"):
        send(chat_id, "Thank you for applying. We don't have a place for you right now.")
        return

    person = Cleaner(id=f"new-{uuid.uuid4().hex[:6]}", name=known["name"], home_area=known["home_area"],
                     telegram_chat_id=chat_id, email=known["email"], notes=f"available: {known['availability']}")
    roster.add_cleaners([person])
    send_email(person.email, "Your work contract: please sign", draft_contract(person))
    person.contract_status = "sent"
    events.log("recruit", f"{person.name} joined the team; work contract sent for signing")
    send(chat_id, "Welcome to the team! Your work contract is in your email, please sign it before your first shift.")
    open_now = roster.open_shifts()
    if open_now:
        send(chat_id, compose(person, open_now))
        roster.mark_asked(person.id, [s.id for s in open_now])
    roster.save()
