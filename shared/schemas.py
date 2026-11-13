"""Data models shared by every module.

Conventions: ids are str, dates "YYYY-MM-DD", times "HH:MM" (24h),
datetimes ISO strings. Missing values stay None; they are never guessed.
Use dataclasses.asdict() to save to data/state.json.
"""
from dataclasses import dataclass, field
from typing import Literal, Optional

Recurrence = Literal["none", "daily", "weekdays"]
ReplyLabel = Literal["yes", "no", "partial", "question", "unclear"]
RosterStatus = Literal["asked", "confirmed", "standby", "declined", "cancelled"]


@dataclass
class Cleaner:
    id: str
    name: str
    home_area: str                 # street or district
    language: str = "en"
    telegram_chat_id: str = ""     # empty until the cleaner sends /start
    simulated: bool = False        # True: replies via the terminal, not Telegram
    notes: str = ""
    email: str = ""                # where a new recruit's work contract is sent
    constraints: list[str] = field(default_factory=list)  # learned from replies, e.g. "never weekends"
    max_travel_minutes: Optional[int] = None  # learned when they say "too far"
    contract_status: str = ""      # "" (existing staff), "sent" or "signed"


@dataclass
class Request:
    id: str
    raw_text: str
    source: Literal["email"] = "email"
    received_at: str = ""          # ISO datetime


@dataclass
class Shift:
    id: str
    request_id: str
    site_name: Optional[str] = None
    address: Optional[str] = None
    date: Optional[str] = None                          # one fixed date
    date_options: list[str] = field(default_factory=list)  # alternatives, e.g. Tue or Wed
    start: Optional[str] = None
    end: Optional[str] = None
    hours_confirmed: bool = False  # True only when the request states the hours as final
    headcount: Optional[int] = None
    recurrence: Recurrence = "none"
    task_summary: str = ""         # one line
    tasks: list[str] = field(default_factory=list)


@dataclass
class OpenQuestion:
    request_id: str
    text: str                      # e.g. "How many people is 'a crew'?"


@dataclass
class Outreach:
    id: str
    cleaner_id: str
    shift_ids: list[str]           # one message can offer several shifts of one request
    text: str
    sent_at: str = ""              # ISO datetime


@dataclass
class Reply:
    id: str
    cleaner_id: str
    raw_text: str
    received_at: str = ""          # ISO datetime
    label: ReplyLabel = "unclear"
    accepted_shift_ids: list[str] = field(default_factory=list)
    question: Optional[str] = None
    constraints: list[str] = field(default_factory=list)  # new standing constraints stated in this reply
    too_far: bool = False          # they declined because of the distance


@dataclass
class RosterEntry:
    shift_id: str
    cleaner_id: str
    status: RosterStatus = "asked"  # shift is full when confirmed entries reach headcount
    agreed_at: Optional[str] = None  # ISO datetime when the cleaner accepted the assignment


@dataclass
class Candidate:
    name: str
    profile_url: str
    comment_text: str
    source: Literal["facebook"] = "facebook"
    fits_shift_ids: list[str] = field(default_factory=list)
    reason: str = ""
