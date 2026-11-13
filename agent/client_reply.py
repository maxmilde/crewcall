"""Draft the email back to the client. The owner approves it before it is sent."""

from agent import roster
from agent.describe import describe
from agent.domain import prompt
from shared.llm import chat_json
from shared.schemas import OpenQuestion, Request, Shift

PROMPT = prompt("client_reply")


def draft_client_reply(request: Request, shifts: list[Shift], questions: list[OpenQuestion]) -> str:
    """Returns the draft as 'Subject: ...' plus the body."""
    status = []
    for s in shifts:
        confirmed = sum(1 for e in roster.entries if e.shift_id == s.id and e.status == "confirmed")
        need = "unknown" if s.headcount is None else s.headcount
        status.append(f"- {describe(s)} | confirmed people: {confirmed} of {need}")
    user = (
        f"Client email:\n{request.raw_text}\n\nStaffing status:\n" + "\n".join(status)
        + "\n\nOpen questions noted by the agent:\n" + "\n".join(f"- {q.text}" for q in questions)
    )
    data = chat_json(PROMPT, user)
    return f"Subject: {data.get('subject', 'Your request')}\n\n{data.get('body', '')}".strip()
