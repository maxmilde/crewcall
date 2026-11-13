"""Telegram bot: send offers to cleaners and pass their replies to a callback.

Plain Bot API over HTTPS with long polling, no extra dependency. Cleaners link
their phone with a deep link, t.me/<bot>?start=c01, which stores the chat id on
roster.cleaners["c01"]. Chat ids that aren't Telegram ids (simulated cleaners)
are printed to the terminal instead. The owner's chat is OWNER_CHAT_ID; without
it, owner messages use the terminal. Run the bot with: python -m integrations.run_bot
"""
import json
import os
import queue
import threading
import time
import traceback
import urllib.error
import urllib.request
from typing import Callable

from dotenv import load_dotenv

from agent import roster

load_dotenv()

_offset = 0  # next update id to fetch
_answers: queue.Queue[str] = queue.Queue()  # owner's answers to ask_owner
_asking = threading.Event()  # set while ask_owner waits for the owner
_ask_lock = threading.Lock()  # one question to the owner at a time


def _api(method: str, **params) -> dict | list:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(params).encode(),
        headers={"Content-Type": "application/json"},
    )
    for attempt in range(3):  # retry connection drops; real API errors (HTTPError) are raised at once
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                return json.load(resp)["result"]
        except urllib.error.HTTPError:
            raise
        except OSError:
            if attempt == 2:
                raise
            time.sleep(1 + attempt)


def _is_telegram(chat_id: str) -> bool:
    return str(chat_id).lstrip("-").isdigit()


def _print(chat_id: str, text: str) -> None:
    print(f"\n  >> to {chat_id}:\n" + "\n".join(f"     {line}" for line in text.splitlines()))


def owner_chat_id() -> str:
    return os.getenv("OWNER_CHAT_ID", "").strip()


def send(chat_id: str, text: str, reply_markup: dict | None = None) -> None:
    if not _is_telegram(chat_id):
        _print(chat_id, text)
        return
    chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)] or [""]  # Telegram limit is 4096
    for i, chunk in enumerate(chunks):
        extra = {"reply_markup": reply_markup} if reply_markup and i == len(chunks) - 1 else {}
        _api("sendMessage", chat_id=int(chat_id), text=chunk, **extra)


def send_buttons(chat_id: str, text: str, buttons: list[str]) -> None:
    """Message with one inline button per label; a tap reaches listen's on_button."""
    if not _is_telegram(chat_id):
        _print(chat_id, f"{text}\n[ {' | '.join(buttons)} ]")
        return
    send(chat_id, text, {"inline_keyboard": [[{"text": b, "callback_data": b[:64]}] for b in buttons]})


QUIET = ("📤", "🧠")  # progress notes the owner doesn't need; she gets the result instead
menu_markup: dict | None = None  # the owner's button menu, set by run_bot
menu_texts: set[str] = set()  # button labels: never taken as an answer to ask_owner


def _quiet(text: str) -> bool:
    """Per-step chatter: offers sent, memory saved, assignment tapped, and reply lines that need nothing from her."""
    if text.startswith(QUIET) or (text.startswith("✍️") and "confirmed the assignment" in text):
        return True  # a signed contract (also ✍️) still reaches her
    return text.startswith("💬") and "\n" in text and "❓" not in text


def notify_owner(text: str) -> None:
    if _quiet(text):
        print("  [owner, muted] " + text.splitlines()[0])
        return
    send(owner_chat_id() or "OWNER", text, menu_markup)


def ask_owner(question: str) -> str:
    """Ask the owner and wait for her next message (listen must be running in another thread)."""
    owner = owner_chat_id()
    if not owner:
        notify_owner(question)
        return input("     owner> ").strip()
    with _ask_lock:
        _asking.set()
        try:
            send(owner, question)
            return _answers.get().strip()
        finally:
            _asking.clear()


def _updates() -> list[dict]:
    global _offset
    updates = _api("getUpdates", offset=_offset, timeout=30, allowed_updates=["message", "callback_query"])
    if updates:
        _offset = updates[-1]["update_id"] + 1
    return updates


def _cleaner_by_chat(chat_id: str) -> str | None:
    return next((c.id for c in roster.cleaners.values() if c.telegram_chat_id == chat_id), None)


def _start(chat_id: str, arg: str) -> bool:
    """/start c01 links this chat to cleaner c01. False if the id is unknown."""
    cleaner = roster.cleaners.get(arg)
    if not cleaner:
        return False
    cleaner.telegram_chat_id = chat_id
    roster.save()
    print(f"  [telegram] {cleaner.id} ({cleaner.name}) linked to chat {chat_id}")
    send(chat_id, f"Hi {cleaner.name}, you're connected. Job offers will arrive here.")
    notify_owner(f"{cleaner.name} ({cleaner.id}) is now connected.")
    return True


def _spawn(fn: Callable, *args) -> None:
    """Handlers run in their own thread so polling continues while they wait on the owner."""
    def run() -> None:
        try:
            fn(*args)
        except Exception:  # one bad message must not stop the bot
            traceback.print_exc()
    threading.Thread(target=run, daemon=True).start()


def _handle(update: dict, on_reply, on_button, on_owner, on_unknown) -> None:
    if cq := update.get("callback_query"):
        _api("answerCallbackQuery", callback_query_id=cq["id"])
        chat_id = str(cq["message"]["chat"]["id"])
        if (cleaner_id := _cleaner_by_chat(chat_id)) and on_button:
            _spawn(on_button, cleaner_id, cq.get("data", ""))
        return
    msg = update.get("message")
    if not msg or "text" not in msg:
        return
    chat_id, text = str(msg["chat"]["id"]), msg["text"].strip()
    if chat_id == owner_chat_id():
        if _asking.is_set() and text not in menu_texts and not text.startswith("/"):
            _answers.put(text)
        elif on_owner and not text.startswith("/start"):
            _spawn(on_owner, msg)
        return
    if text.startswith("/start") and _start(chat_id, text.removeprefix("/start").strip()):
        return
    if cleaner_id := _cleaner_by_chat(chat_id):
        _spawn(on_reply, cleaner_id, text)
    elif on_unknown:
        _spawn(on_unknown, chat_id, text)
    else:
        print(f"  [telegram] message from unknown chat {chat_id}: {text}")


def listen(on_reply: Callable[[str, str], None],
           on_button: Callable[[str, str], None] | None = None,
           on_owner: Callable[[dict], None] | None = None,
           on_unknown: Callable[[str, str], None] | None = None) -> None:
    """Poll forever. Known cleaners -> on_reply(cleaner_id, text), button taps -> on_button(cleaner_id, label),
    the owner's messages -> on_owner(message) (or ask_owner's answer), anyone else -> on_unknown(chat_id, text)."""
    while True:
        try:
            updates = _updates()
        except OSError as e:  # timeouts and network drops: wait and poll again
            print(f"  [telegram] poll failed ({e}); retrying")
            time.sleep(2)
            continue
        for update in updates:
            try:
                _handle(update, on_reply, on_button, on_owner, on_unknown)
            except Exception:
                traceback.print_exc()


def load_cleaners() -> None:
    """The owner's contact list; roster.save() writes linked chat ids back into it."""
    roster.load_cleaners_csv()
