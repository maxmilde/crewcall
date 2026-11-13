"""Understand a cleaner's free-text reply to an offer."""
import uuid
from datetime import datetime

from agent.describe import describe
from agent.domain import prompt
from shared.llm import chat_json
from shared.schemas import Reply, Shift

CLASSIFY_PROMPT = prompt("classify")
LABELS = {"yes", "no", "partial", "question", "unclear"}


def classify(reply_text: str, offered_shifts: list[Shift], cleaner_id: str = "") -> Reply:
    """Label the reply and list which offered shifts were accepted."""
    offered = "\n".join(f"- {describe(s, with_id=True)}" for s in offered_shifts)
    data = chat_json(CLASSIFY_PROMPT, f"Offered shifts:\n{offered}\n\nReply:\n{reply_text}")

    offered_ids = [s.id for s in offered_shifts]
    label = data.get("label") if data.get("label") in LABELS else "unclear"
    accepted = [i for i in offered_ids if i in (data.get("accepted_shift_ids") or [])]
    # Keep label and accepted ids consistent, whatever the model returned.
    if label == "yes":
        accepted = offered_ids
    elif label == "no":
        accepted = []
    elif label == "partial" and not accepted:
        label = "unclear"
    elif label == "partial" and len(accepted) == len(offered_ids):
        label = "yes"

    question = data.get("question")
    constraints = [c.strip() for c in data.get("constraints") or [] if isinstance(c, str) and c.strip()]
    return Reply(
        id=uuid.uuid4().hex[:8],
        cleaner_id=cleaner_id,
        raw_text=reply_text,
        received_at=datetime.now().isoformat(timespec="seconds"),
        label=label,
        accepted_shift_ids=accepted,
        question=question.strip() if isinstance(question, str) and question.strip() else None,
        constraints=constraints,
    )
