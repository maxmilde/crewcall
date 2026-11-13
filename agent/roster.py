"""Who is on which shift. State lives in memory and is saved to data/state.json."""
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from agent.describe import describe
from shared.schemas import Cleaner, Reply, RosterEntry, Shift

STATE_FILE = Path("data/state.json")

shifts: dict[str, Shift] = {}
cleaners: dict[str, Cleaner] = {}
entries: list[RosterEntry] = []


def add_shifts(new: list[Shift]) -> None:
    shifts.update({s.id: s for s in new})


def add_cleaners(new: list[Cleaner]) -> None:
    cleaners.update({c.id: c for c in new})


def _entry(cleaner_id: str, shift_id: str) -> RosterEntry | None:
    return next((e for e in entries if e.cleaner_id == cleaner_id and e.shift_id == shift_id), None)


def _confirmed(shift_id: str) -> list[RosterEntry]:
    return [e for e in entries if e.shift_id == shift_id and e.status == "confirmed"]


def is_full(shift_id: str) -> bool:
    headcount = shifts[shift_id].headcount
    return headcount is not None and len(_confirmed(shift_id)) >= headcount


def mark_asked(cleaner_id: str, shift_ids: list[str]) -> None:
    """Record that an offer went out (a re-offer after a cancellation resets the entry)."""
    for shift_id in shift_ids:
        entry = _entry(cleaner_id, shift_id)
        if entry is None:
            entries.append(RosterEntry(shift_id=shift_id, cleaner_id=cleaner_id))
        elif entry.status != "confirmed":
            entry.status, entry.agreed_at = "asked", None


def apply(reply: Reply) -> list[str]:
    """Update the roster from a classified reply. Returns readable notes on what changed."""
    notes = []
    cleaner = cleaners.get(reply.cleaner_id)
    name = cleaner.name if cleaner else reply.cleaner_id
    if cleaner:
        for rule in reply.constraints:
            if rule not in cleaner.constraints:
                cleaner.constraints.append(rule)
                notes.append(f"Remembered for {name}: {rule}")
    if reply.label in ("question", "unclear"):
        return notes
    for entry in entries:
        if entry.cleaner_id != reply.cleaner_id or entry.status != "asked":
            continue
        if entry.shift_id in reply.accepted_shift_ids:
            if is_full(entry.shift_id):
                notes.append(f"{name} said yes to {entry.shift_id}, but it is already full")
                entry.status = "declined"
            else:
                entry.status = "confirmed"
                notes.append(f"{name} confirmed {entry.shift_id}")
        else:
            entry.status = "declined"
            notes.append(f"{name} declined {entry.shift_id}")
    return notes


def agree(cleaner_id: str, shift_id: str) -> None:
    """The cleaner accepted the assignment confirmation."""
    entry = _entry(cleaner_id, shift_id)
    if entry and entry.status == "confirmed":
        entry.agreed_at = datetime.now().isoformat(timespec="seconds")


def cancel(cleaner_id: str, shift_id: str) -> None:
    """A confirmed cleaner dropped out: the slot reopens."""
    entry = _entry(cleaner_id, shift_id)
    if entry:
        entry.status, entry.agreed_at = "cancelled", None


def open_shifts() -> list[Shift]:
    """Shifts still missing people. Unknown headcount counts as open until the owner sets it."""
    return [s for s in shifts.values() if not is_full(s.id)]


def asked_before(shift_id: str) -> set[str]:
    """Cleaners already offered this shift, so a re-staffing round skips them."""
    return {e.cleaner_id for e in entries if e.shift_id == shift_id}


def _name(cleaner_id: str) -> str:
    return cleaners[cleaner_id].name if cleaner_id in cleaners else cleaner_id


def summary() -> str:
    lines = []
    for shift in shifts.values():
        confirmed = _confirmed(shift.id)
        names = [_name(e.cleaner_id) + (" (agreed)" if e.agreed_at else "") for e in confirmed]
        pending = [_name(e.cleaner_id) for e in entries if e.shift_id == shift.id and e.status == "asked"]
        need = "?" if shift.headcount is None else str(shift.headcount)
        status = "FULL" if is_full(shift.id) else "OPEN"
        lines.append(f"[{status}] {shift.id}: {describe(shift)}")
        lines.append(f"    confirmed {len(confirmed)}/{need}: {', '.join(names) or '-'}")
        if pending:
            lines.append(f"    waiting for: {', '.join(pending)}")
    return "\n".join(lines) or "No shifts yet."


def save() -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "shifts": [asdict(s) for s in shifts.values()],
        "cleaners": [asdict(c) for c in cleaners.values()],
        "entries": [asdict(e) for e in entries],
    }
    STATE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def load() -> None:
    if not STATE_FILE.exists():
        return
    data = json.loads(STATE_FILE.read_text())
    shifts.clear(), cleaners.clear(), entries.clear()
    add_shifts([Shift(**s) for s in data["shifts"]])
    add_cleaners([Cleaner(**c) for c in data["cleaners"]])
    entries.extend(RosterEntry(**e) for e in data["entries"])
