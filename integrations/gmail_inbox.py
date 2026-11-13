"""Client requests arrive in a work Gmail inbox; each new email starts the workflow.

Needs GMAIL_ADDRESS and GMAIL_APP_PASSWORD in .env (a Google app password, not the
account password). Reads only unread mail in INBOX and marks it read once handled.
"""
import email
import imaplib
import os
import re
import threading
import time
from datetime import datetime
from email.header import decode_header, make_header
from email.utils import parseaddr
from typing import Callable

from dotenv import load_dotenv

from shared.schemas import Request

load_dotenv()
POLL_SECONDS = 10
SKIP_SENDERS = ("no-reply", "noreply", "do-not-reply", "mailer-daemon", "@accounts.google.com", "@google.com")


def _automatic(msg: email.message.Message) -> bool:
    """Notifications from Google and other robots are not client requests."""
    sender = parseaddr(msg.get("From", ""))[1].lower()
    return any(s in sender for s in SKIP_SENDERS) or msg.get("Auto-Submitted", "no").lower() != "no"


def _text(msg: email.message.Message) -> str:
    """Plain-text body; falls back to HTML with the tags stripped."""
    parts = msg.walk() if msg.is_multipart() else [msg]
    plain, html = "", ""
    for part in parts:
        if part.get_content_maintype() == "multipart" or part.get("Content-Disposition", "").startswith("attachment"):
            continue
        payload = part.get_payload(decode=True) or b""
        body = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        if part.get_content_type() == "text/plain" and not plain:
            plain = body
        elif part.get_content_type() == "text/html" and not html:
            html = re.sub(r"<[^>]+>", " ", body)
    return (plain or html).strip()


def _client_id(msg: email.message.Message, taken: set[str]) -> str:
    """Short readable id for messages, from the sender's name, e.g. "anna" or "gymclub"."""
    name, address = parseaddr(str(make_header(decode_header(msg.get("From", "")))))
    base = re.sub(r"[^a-z0-9]", "", (name.split()[0] if name else address.split("@")[0]).lower())[:12] or "client"
    client, n = base, 2
    while client in taken:
        client, n = f"{base}{n}", n + 1
    return client


def fetch_new(taken: set[str] = frozenset()) -> list[Request]:
    """Unread emails as requests (marks them read)."""
    box = imaplib.IMAP4_SSL("imap.gmail.com")
    box.login(os.environ["GMAIL_ADDRESS"], os.environ["GMAIL_APP_PASSWORD"])
    box.select("INBOX")
    requests = []
    _, ids = box.search(None, "UNSEEN")
    for num in ids[0].split():
        _, data = box.fetch(num, "(RFC822)")  # fetching marks the message as read
        msg = email.message_from_bytes(data[0][1])
        if _automatic(msg):
            continue  # fetched, so already marked read
        subject = str(make_header(decode_header(msg.get("Subject", ""))))
        client = _client_id(msg, set(taken) | {r.id for r in requests})
        requests.append(Request(id=client, raw_text=f"Subject: {subject}\n\n{_text(msg)}",
                                received_at=datetime.now().isoformat(timespec="seconds")))
    box.logout()
    return requests


def watch(on_requests: Callable[[list[Request]], None], taken: Callable[[], set[str]] = set) -> threading.Thread:
    """Check the inbox every POLL_SECONDS in the background and hand new requests over."""
    def loop():
        while True:
            try:
                new = fetch_new(taken())
                if new:
                    on_requests(new)
            except Exception as error:  # a network hiccup must not stop the agent
                print(f"[inbox] {type(error).__name__}: {error}")
            time.sleep(POLL_SECONDS)

    if not (os.getenv("GMAIL_ADDRESS") and os.getenv("GMAIL_APP_PASSWORD")):
        print("[inbox] GMAIL_ADDRESS / GMAIL_APP_PASSWORD not set: inbox not watched")
        return None
    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    print(f"[inbox] watching {os.environ['GMAIL_ADDRESS']}")
    return thread


if __name__ == "__main__":  # check the connection: lists unread mail without starting anything
    for r in fetch_new():
        print(f"--- {r.id}\n{r.raw_text[:300]}\n")
