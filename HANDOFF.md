# HANDOFF.md

Message board between Agent A (Max) and Agent B (Zahid). Newest entry at the top.
Proposals to change the plan go here too; a human decides and updates the project doc.

Format:

```
## HH:MM — Agent A (Max) | Agent B (Zahid)
Done: <files and functions finished, with their signatures>
Needs from A/B: <what you need from the other agent, if anything>
Blocked on: <blocker, or "nothing">
```

---

<!-- entries start below this line -->

## 13 Nov — Agent A (Max)
Done (branch max/replies, built on max/intake + latest max/schemas):
- agent/outreach.py: compose(cleaner: Cleaner, shifts: list[Shift]) -> str. Under 60 words, PAY_TEXT from .env, ends "Reply yes, no, or which days you can do."
- agent/replies.py: classify(reply_text: str, offered_shifts: list[Shift], cleaner_id: str = "") -> Reply. "Only Thursday" -> partial with the Thursday shift; also fills Reply.constraints ("never Thursdays") for cleaner memory.
- agent/describe.py: describe(shift) -> one readable line, used by the prompts.
Schema draft updated on max/schemas: Cleaner.email, Cleaner.constraints, Reply.constraints, RosterEntry.agreed_at, RosterStatus "cancelled". Please include these in your review.
Needs from B: when listen() gets a reply, pass the cleaner id so classify can fill Reply.cleaner_id.
Blocked on: nothing.

## 13 Nov — Agent A (Max)
Done: agent/intake.py on branch max/intake (built on max/schemas + max/llm): parse_request(request: Request) -> tuple[list[Shift], list[OpenQuestion]]. Prompt in agent/prompts/intake.txt; the three example emails in data/requests/. Email 3 gives 4 shifts (date options, unconfirmed hours) and asks the owner for crew size and hours, ~7 s per email. Run: .venv/bin/python -m agent.intake data/requests/email3.txt
Model changed: FEATHERLESS_MODEL=deepseek-ai/DeepSeek-V4.1-Flash (Qwen 72B on Featherless returned "!!!!" garbage). It thinks before answering, so chat_json allows 8000 tokens.
Needs from B: nothing.
Blocked on: nothing.

## 13 Nov — Agent A (Max)
Done: shared/llm.py on branch max/llm: chat_json(system: str, user: str) -> dict. Featherless via the openai client, temperature 0, retries once on invalid JSON, then raises ValueError. Live call works with FEATHERLESS_MODEL=Qwen/Qwen2.5-72B-Instruct (~5 s).
New dependencies: openai, python-dotenv (requirements.txt). Setup: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
Needs from B: nothing.
Blocked on: nothing.

## 13 Nov — Agent A (Max)
Done: shared/schemas.py draft on branch max/schemas (not merged): Cleaner, Request, Shift, OpenQuestion, Outreach, Reply, RosterEntry, Candidate as dataclasses. Conventions under "Schema conventions" in the doc. Shift.hours_confirmed defaults to False (set True only when the request states final hours). Added empty shared/__init__.py.
Needs from B: review schemas.py, especially Cleaner (Telegram fields may change once your bot design is clear) and Candidate. Then the humans freeze it.
Blocked on: nothing.
