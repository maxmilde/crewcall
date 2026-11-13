"""Plain-text descriptions of shifts, shared by the prompts."""
from datetime import date

from shared.schemas import Shift


def _day(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d:%A} {d.day} {d:%B}"  # e.g. "Thursday 19 November"


def when(shift: Shift) -> str:
    if shift.date:
        days = _day(shift.date)
    elif shift.date_options:
        days = " or ".join(_day(d) for d in shift.date_options)
    else:
        days = "start date to be agreed"
    if shift.recurrence == "daily":
        days += ", every day"
    elif shift.recurrence == "weekdays":
        days += ", Monday to Friday"
    if shift.start and shift.end:
        hours = f"{shift.start}–{shift.end}"
        if not shift.hours_confirmed:
            hours = f"roughly {hours}, to be confirmed"
    else:
        hours = "hours to be confirmed"
    return f"{days}, {hours}"


def where(shift: Shift) -> str:
    parts = [p for p in (shift.site_name, shift.address) if p]
    return ", ".join(parts) or "location to be confirmed"


def describe(shift: Shift, with_id: bool = False) -> str:
    line = f"{when(shift)} at {where(shift)}: {shift.task_summary}"
    return f"[{shift.id}] {line}" if with_id else line


def job_name(request_id: str) -> str:
    """Short name for a job: the client's first word ("Gym", "Event") when known, else its id."""
    from agent.intake import client_names
    name = client_names.get(request_id, "")
    first = name.replace("(", " ").split()[0] if name.strip() else ""
    return first if first and not first.startswith("[") else request_id


def label(shift: Shift) -> str:
    """Short name for messages on a phone, e.g. "Thu event 12–17" or "Daily gym 06–09"."""
    if shift.recurrence == "daily":
        day = "Daily"
    elif shift.recurrence == "weekdays":
        day = "Mon–Fri"
    elif shift.date:
        day = f"{date.fromisoformat(shift.date):%a}"
    elif shift.date_options:
        day = "/".join(f"{date.fromisoformat(d):%a}" for d in shift.date_options)
    else:
        return f"{job_name(shift.request_id)} (date tbc)"
    hours = f"{shift.start[:2]}–{shift.end[:2]}" if shift.start and shift.end else ""
    if hours and not shift.hours_confirmed:
        hours = "~" + hours
    return f"{day} {job_name(shift.request_id)} {hours}".strip()
