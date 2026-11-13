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
