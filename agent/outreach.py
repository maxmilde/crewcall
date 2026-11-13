"""Messages to cleaners: job offers for shifts."""
import os
from pathlib import Path

from agent.describe import describe
from shared.llm import chat_json
from shared.schemas import Cleaner, Shift

PROMPTS = Path(__file__).parent / "prompts"
COMPOSE_PROMPT = (PROMPTS / "compose.txt").read_text()
CLOSING = "Reply yes, no, or which days you can do."


def compose(cleaner: Cleaner, shifts: list[Shift]) -> str:
    """Short offer in the cleaner's language: place, days and hours, task, pay."""
    pay = os.getenv("PAY_TEXT", "Pay according to legal rates")
    shift_lines = "\n".join(f"- {describe(s)}" for s in shifts)
    user = (
        f"Cleaner: {cleaner.name}\nLanguage: {cleaner.language}\n"
        f"Pay text: {pay}\nShifts:\n{shift_lines}"
    )
    text = str(chat_json(COMPOSE_PROMPT, user).get("text", "")).strip()
    if not text.endswith(CLOSING):
        text = f"{text}\n{CLOSING}".strip()
    return text
