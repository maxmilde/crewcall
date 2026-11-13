"""Same agent, another line of work: an event-staffing email read and staffed with DOMAIN=events.

Run: .venv/bin/python -m agent.other_domain [email file]
"""
import os
import sys
from pathlib import Path

os.environ["DOMAIN"] = "events"  # before the agent modules read their settings

from agent.describe import describe  # noqa: E402
from agent.intake import parse_request  # noqa: E402
from agent.outreach import compose  # noqa: E402
from shared.schemas import Cleaner, Request  # noqa: E402

path = Path(sys.argv[1] if len(sys.argv) > 1 else "data/requests/events_email.txt")
shifts, questions = parse_request(Request(id="conference", raw_text=path.read_text(), received_at="2026-11-13T09:00:00"))
print("SAME AGENT, EVENT STAFFING\n")
for s in shifts:
    print(f"  {describe(s)} | {s.headcount or '?'} people")
for q in questions:
    print(f"  ? {q.text}")
print("\nOffer to a helper:\n")
print("  " + compose(Cleaner("h1", "Tereza", "Karlín"), shifts[:1]).replace("\n", "\n  "))
