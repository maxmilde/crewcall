"""Turn a client email into shifts to staff plus open questions for the owner."""
import re
from datetime import date
from pathlib import Path

from agent.domain import prompt
from shared.llm import chat_json
from shared.schemas import OpenQuestion, Request, Shift

PROMPT = prompt("intake")
RECURRENCES = {"none", "daily", "weekdays"}
client_names: dict[str, str] = {}  # request id -> company name from the email, for the owner's messages


def _iso_date(value) -> str | None:
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()).isoformat()
        except ValueError:
            return None
    return None


def _time(value) -> str | None:
    if isinstance(value, str) and re.fullmatch(r"\d{1,2}:\d{2}", value.strip()):
        hours, minutes = value.strip().split(":")
        return f"{int(hours):02d}:{minutes}"
    return None


def _headcount(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.strip().isdigit() and int(value) > 0:
        return int(value)
    return None


def _text(value) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _to_shift(raw: dict, request_id: str, number: int) -> Shift:
    options = [d for d in (_iso_date(v) for v in raw.get("date_options") or []) if d]
    recurrence = raw.get("recurrence")
    return Shift(
        id=f"{request_id}-s{number}",
        request_id=request_id,
        site_name=_text(raw.get("site_name")),
        address=_text(raw.get("address")),
        date=_iso_date(raw.get("date")),
        date_options=options,
        start=_time(raw.get("start")),
        end=_time(raw.get("end")),
        hours_confirmed=raw.get("hours_confirmed") is True,
        headcount=_headcount(raw.get("headcount")),
        recurrence=recurrence if recurrence in RECURRENCES else "none",
        task_summary=_text(raw.get("task_summary")) or "",
        tasks=[t.strip() for t in raw.get("tasks") or [] if isinstance(t, str) and t.strip()],
    )


def parse_request(request: Request) -> tuple[list[Shift], list[OpenQuestion]]:
    """Ask the model for shifts and questions, then clean the values it returns."""
    received = request.received_at or date.today().isoformat()
    user = f"Email received on: {received}\n\n{request.raw_text}"
    data = chat_json(PROMPT, user)
    if isinstance(data.get("client"), str) and data["client"].strip():
        client_names[request.id] = data["client"].strip()
    shifts = [
        _to_shift(raw, request.id, i)
        for i, raw in enumerate(data.get("shifts") or [], start=1)
        if isinstance(raw, dict)
    ]
    questions = [
        OpenQuestion(request_id=request.id, text=q.strip())
        for q in data.get("questions") or []
        if isinstance(q, str) and q.strip()
    ]
    return shifts, questions


if __name__ == "__main__":
    import sys

    path = Path(sys.argv[1] if len(sys.argv) > 1 else "data/requests/email3.txt")
    req = Request(id=path.stem, raw_text=path.read_text(), received_at="2026-11-13T09:00:00")
    shifts, questions = parse_request(req)
    for s in shifts:
        when = s.date or " or ".join(s.date_options) or "date ?"
        hours = f"{s.start or '?'}–{s.end or '?'}" + ("" if s.hours_confirmed else " (not confirmed)")
        print(f"{s.id}: {when} {hours} | {s.headcount or '?'} people | {s.recurrence} | {s.task_summary}")
    for q in questions:
        print(f"QUESTION: {q.text}")
