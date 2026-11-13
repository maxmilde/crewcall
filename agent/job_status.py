"""One status message per job in the owner's chat, edited in place as people answer.

Instead of a new message for every reply, the owner sees one card per client request
that always shows who is booked, who we're waiting for and what's still open.
Without Telegram (no OWNER_CHAT_ID) the cards are printed instead.
"""
import threading

from agent import roster
from agent.describe import label
from agent.intake import client_names

_messages: dict[str, int] = {}  # request id -> Telegram message id of its card
_shown: dict[str, str] = {}     # request id -> text currently on the card
_lock = threading.Lock()


def card(request_id: str) -> str:
    shifts = [s for s in roster.shifts.values() if s.request_id == request_id]
    lines = [f"📋 {client_names.get(request_id, request_id)}"]
    full = 0
    for s in shifts:
        mine = [e for e in roster.entries if e.shift_id == s.id]
        names = lambda status: [roster._name(e.cleaner_id) + (" ✍️" if e.agreed_at else "") for e in mine if e.status == status]
        booked, waiting, standby = names("confirmed"), names("asked"), names("standby")
        need = s.headcount or 0
        done = need and len(booked) >= need
        full += bool(done)
        line = f"{'✅' if done else '🟠'} {label(s)}: {len(booked)}/{need or '?'}"
        if booked:
            line += "  " + ", ".join(booked)
        if waiting and not done:
            line += f"\n      ⏳ {', '.join(waiting)}"
        if standby:
            line += f"\n      ⏸ standby: {', '.join(standby)}"
        lines.append(line)
    lines.append("All booked ✅" if shifts and full == len(shifts) else f"{full}/{len(shifts)} shifts full")
    return "\n".join(lines)


def _post(request_id: str, text: str) -> None:
    from integrations import telegram_bot as bot
    owner = bot.owner_chat_id()
    if not bot._is_telegram(owner):
        bot._print("OWNER (card)", text)
        return
    if request_id in _messages:
        bot._api("editMessageText", chat_id=owner, message_id=_messages[request_id], text=text)
    else:
        _messages[request_id] = bot._api("sendMessage", chat_id=owner, text=text)["message_id"]


def refresh() -> None:
    """Update every job card whose content changed (cheap: unchanged cards are skipped)."""
    with _lock:
        for request_id in dict.fromkeys(s.request_id for s in roster.shifts.values()):
            if not any(roster.shifts[e.shift_id].request_id == request_id
                       for e in roster.entries if e.shift_id in roster.shifts):
                continue  # nobody asked yet: no card until offers go out
            text = card(request_id)
            if _shown.get(request_id) == text:
                continue
            try:
                _post(request_id, text)
                _shown[request_id] = text
            except Exception as error:  # a failed edit must never stop the agent
                print(f"[job card] {type(error).__name__}: {error}")
