"""Simulated work documents, filled from fixed templates (no model, so no invented terms)."""
import os
from datetime import date
from pathlib import Path

from agent.describe import when, where
from shared.schemas import Cleaner, Shift

TEMPLATES = Path(__file__).parent.parent / "data" / "templates"


def _common() -> dict:
    return {
        "company": os.getenv("COMPANY_NAME", "[Company]"),
        "pay": os.getenv("PAY_TEXT", "Pay according to legal rates"),
        "city": os.getenv("CITY", "Prague"),
        "role": os.getenv("ROLE", "Cleaner"),
    }


def draft_contract(person: Cleaner) -> str:
    """Work contract for a new recruit, sent by email."""
    template = (TEMPLATES / "work_contract.md").read_text()
    return template.format(
        **_common(), name=person.name, home_area=person.home_area or "address on file",
        start_date=date.today().isoformat(),
    )


def draft_assignment(cleaner: Cleaner, shifts: list[Shift]) -> str:
    """Short confirmation of the shifts a pool cleaner accepted, sent on Telegram."""
    lines = "\n".join(
        f"- {when(s)}\n  Site: {where(s)}\n  Tasks: {', '.join(s.tasks) or s.task_summary}"
        for s in shifts
    )
    template = (TEMPLATES / "assignment.md").read_text()
    return template.format(**_common(), name=cleaner.name, shift_lines=lines)
