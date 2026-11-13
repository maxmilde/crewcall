"""Messages to workers: job offers for shifts, and the public job post for open shifts."""

from agent.describe import describe
from agent.domain import prompt, settings
from shared.llm import chat_json
from shared.schemas import Cleaner, Shift

COMPOSE_PROMPT = prompt("compose")
CLOSING = "Reply yes, no, or which days you can do."


def compose(cleaner: Cleaner, shifts: list[Shift]) -> str:
    """Short offer in the cleaner's language: place, days and hours, task, pay."""
    pay = settings()["pay_text"]
    shift_lines = "\n".join(f"- {describe(s)}" for s in shifts)
    user = (
        f"Cleaner: {cleaner.name}\nLanguage: {cleaner.language}\n"
        f"Pay text: {pay}\nShifts:\n{shift_lines}"
    )
    try:
        text = str(chat_json(COMPOSE_PROMPT, user, max_tokens=3000).get("text", "")).strip()
    except ValueError:  # never let one bad model answer stop the offers
        first = cleaner.name.split()[0]
        text = f"Hi {first}, work available:\n{shift_lines}\n{pay}."
    if not text.endswith(CLOSING):
        text = f"{text}\n{CLOSING}".strip()
    return text


DRAFT_POST_PROMPT = prompt("draft_post")


def draft_post(open_shifts: list[Shift]) -> str:
    """Facebook group post in the owner's style for shifts still open. She posts it herself."""
    lines = "\n".join(
        f"- {describe(s)} | people needed: {s.headcount or 'some'}" for s in open_shifts
    )
    return str(chat_json(DRAFT_POST_PROMPT, f"Open shifts:\n{lines}").get("text", "")).strip()
