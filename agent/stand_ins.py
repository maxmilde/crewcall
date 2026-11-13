"""Terminal stand-ins for the Telegram and Apify integrations, with the same signatures.

The workflow uses the real integrations when they exist and these otherwise,
so the whole flow can run on one laptop with simulated workers.
"""
import zlib

from shared.schemas import Cleaner, Shift


def send(chat_id: str, text: str) -> None:
    print(f"\n  >> to {chat_id}:\n" + "\n".join(f"     {line}" for line in text.splitlines()))


def send_buttons(chat_id: str, text: str, buttons: list[str]) -> None:
    send(chat_id, f"{text}\n[ {' | '.join(buttons)} ]")


def notify_owner(text: str) -> None:
    print("\n  >> to OWNER:\n" + "\n".join(f"     {line}" for line in text.splitlines()))


def ask_owner(question: str) -> str:
    notify_owner(question)
    return input("     owner> ").strip()


def travel_minutes(cleaners: list[Cleaner], address: str, arrive_by: str) -> dict[str, int]:
    """Fake but stable transit times (10–60 min) per cleaner area."""
    return {c.id: 10 + zlib.crc32(f"{c.home_area}|{address}".encode()) % 51 for c in cleaners}


def shortlist(shift: Shift, cleaners: list[Cleaner], minutes: dict[str, int]) -> list[Cleaner]:
    """Nearest first; no hard cut-off."""
    return sorted((c for c in cleaners if c.id in minutes), key=lambda c: minutes[c.id])
