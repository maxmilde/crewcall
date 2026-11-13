"""Telegram bot: send offers to cleaners and pass their replies to a callback.

Plain Bot API over HTTPS with long polling, no extra dependency. Cleaners link
their phone with a deep link, t.me/<bot>?start=c01, which stores the chat id on
roster.cleaners["c01"]. Chat ids that aren't Telegram ids (simulated cleaners)
are printed to the terminal instead.
"""
import json
import os
import sys
import time
import traceback
import urllib.request
from typing import Callable

from dotenv import load_dotenv

from agent import roster

load_dotenv()

_offset = 0  # next update id to fetch


def _api(method: str, **params) -> dict | list:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(params).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=40) as resp:
        return json.load(resp)["result"]


def _is_telegram(chat_id: str) -> bool:
    return str(chat_id).lstrip("-").isdigit()


def _print(chat_id: str, text: str) -> None:
    print(f"\n  >> to {chat_id}:\n" + "\n".join(f"     {line}" for line in text.splitlines()))


def send(chat_id: str, text: str) -> None:
    if _is_telegram(chat_id):
        _api("sendMessage", chat_id=int(chat_id), text=text)
    else:
        _print(chat_id, text)


def _updates() -> list[dict]:
    global _offset
    updates = _api("getUpdates", offset=_offset, timeout=30, allowed_updates=["message", "callback_query"])
    if updates:
        _offset = updates[-1]["update_id"] + 1
    return updates


def _cleaner_by_chat(chat_id: str) -> str | None:
    return next((c.id for c in roster.cleaners.values() if c.telegram_chat_id == chat_id), None)


def _start(chat_id: str, arg: str) -> None:
    """/start c01 links this chat to cleaner c01."""
    cleaner = roster.cleaners.get(arg)
    if not cleaner:
        print(f"  [telegram] /start {arg or '(no id)'} from unknown chat {chat_id}")
        return
    cleaner.telegram_chat_id = chat_id
    roster.save()
    print(f"  [telegram] {cleaner.id} ({cleaner.name}) linked to chat {chat_id}")
    send(chat_id, f"Hi {cleaner.name}, you're connected. Job offers will arrive here.")


def listen(on_reply: Callable[[str, str], None]) -> None:
    """Poll forever; call on_reply(cleaner_id, text) for each message from a known cleaner."""
    while True:
        try:
            updates = _updates()
        except OSError as e:  # timeouts and network drops: wait and poll again
            print(f"  [telegram] poll failed ({e}); retrying")
            time.sleep(2)
            continue
        for update in updates:
            msg = update.get("message")
            if not msg or "text" not in msg:
                continue
            chat_id, text = str(msg["chat"]["id"]), msg["text"].strip()
            try:
                if text.startswith("/start"):
                    _start(chat_id, text.removeprefix("/start").strip())
                elif cleaner_id := _cleaner_by_chat(chat_id):
                    on_reply(cleaner_id, text)
                else:
                    print(f"  [telegram] message from unknown chat {chat_id}: {text}")
            except Exception:  # one bad message must not stop the bot
                traceback.print_exc()


def load_cleaners() -> None:
    """The owner's contact list; roster.save() writes linked chat ids back into it."""
    roster.load_cleaners_csv()


if __name__ == "__main__":
    # Test: python -m integrations.telegram_bot c01 -> open the link, reply, see it print.
    load_cleaners()
    cid = sys.argv[1] if len(sys.argv) > 1 else "c01"
    bot = _api("getMe")["username"]
    print(f"Link for {cid}: https://t.me/{bot}?start={cid}")
    chat = roster.cleaners[cid].telegram_chat_id
    if chat:
        send(chat, "Test offer: reply anything.")
    listen(lambda cleaner_id, text: print(f"{cleaner_id}: {text}"))
