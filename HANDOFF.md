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
Done (branch max/evals): agent/evals.py, 58 test cases over every AI step (classify, intake, compose, post, decide, owner chat, travel, applicants). Run: .venv/bin/python -m agent.evals [area]. 58/58 pass, ~15 s. Prompt fixes: conditional yeses and "wrong number" go to the owner; quote-only emails still produce a question for the owner.
Needs from B: nothing. If you add AI steps (rank), feel free to add a test area in your own file.
Blocked on: nothing.

## 13 Nov — Agent A (Max)
Done (branch max/owner-chat):
- agent/owner_chat.py: handle(text) -> str. Owner's plain-language messages: "who's on Friday?", "add one more person Thursday", "take Anna off Friday", "client reply". Model picks one allowed action; code checks it before anything changes.
- agent/applicants.py: greeting() -> str, on_applicant(chat_id, text). Facebook applicants: collects name, area, availability, email; owner approves; contract by email; offers for open shifts.
- stand_ins.send_email(to, subject, body).
Needs from B (Telegram bot routing):
- messages from OWNER_CHAT_ID -> owner_chat.handle(text), send the result back to the owner
- known worker -> workflow.on_reply(cleaner_id, text); button tap -> workflow.on_button(cleaner_id, button)
- unknown chat, or /start apply (the link in the Facebook post: t.me/<bot>?start=apply) -> send applicants.greeting() first, then applicants.on_applicant(chat_id, text)
- integrations/email.py: send_email(to, subject, body) (SMTP, or print as fallback)
Blocked on: nothing.

## 13 Nov — Agent A (Max)
Done (branch max/workflow, built on max/post-domain): agent/workflow.py, the "Agent workflow" from the doc.
- start(request) -> shifts: parse, owner sets missing headcounts and approves. staff(shifts): 2N nearest per shift, one offer per worker covering all their shifts, written in parallel, travel time added to the offer.
- on_reply(cleaner_id, text), on_button(cleaner_id, "I agree"), on_cancel(cleaner_id, shift_id): roster updates, assignment with button, "too far" follow-up (saves max_travel_minutes + area), standby first on cancellation.
- next_steps/decide: the only AI decision. For open shifts where everyone answered: ask_more | facebook_post | tell_owner, with code guards. client_reply(): draft for the owner only.
- agent/stand_ins.py: terminal versions of send, send_buttons, notify_owner, ask_owner, travel_minutes, shortlist. workflow.py imports your real ones when they exist (integrations.telegram_bot, integrations.apify_travel, agent.matching), else the stand-ins.
- agent/simulate.py: full scripted run, no Telegram/Apify needed: .venv/bin/python -m agent.simulate
- chat_json: thinking is now OFF by default (chat_template_kwargs thinking=false): same quality, 3-5x faster, no runaway replies. Optional max_tokens and think=True.
- Schema (draft): Cleaner.max_travel_minutes, Reply.too_far, RosterStatus "standby".
- .gitignore: data/state*.json.
Needs from B: in integrations/telegram_bot.py please also provide notify_owner(text) and ask_owner(question) -> str (owner's chat, OWNER_CHAT_ID in .env), and send_buttons(chat_id, text, buttons). listen should call workflow.on_reply(cleaner_id, text) / on_button(cleaner_id, button). shortlist: nearest first, no cut-off (workflow takes the first 2N and applies each worker's learned max).
Blocked on: nothing.

## 13 Nov — Agent A (Max)
Done (branch max/post-domain):
- agent/outreach.py: draft_post(open_shifts: list[Shift]) -> str. Facebook post in the owner's style, "good pay", no amounts or invented benefits.
- Domain config: data/domains/cleaning.json and events.json; DOMAIN in .env picks one (default cleaning). agent/domain.py: settings(), prompt(name), fill(text). All prompts and document templates now use it, so DOMAIN=events staffs event helpers with the same code.
- .env.example: DOMAIN added; ROLE removed (now in the domain file); PAY_TEXT optional (overrides the domain pay text).
Needs from B: if your rank() prompt mentions cleaning, you can use agent.domain.settings()["worker"] instead.
Blocked on: nothing.

## 13 Nov — Agent A (Max)
Done (branch max/documents, built on max/roster):
- agent/documents.py: draft_contract(person: Cleaner) -> str (work contract for a new recruit, to send by email), draft_assignment(cleaner: Cleaner, shifts: list[Shift]) -> str (to send on Telegram with an "I agree" button). Both filled from data/templates/, marked SAMPLE, no model involved.
- agent/client_reply.py: draft_client_reply(request, shifts, questions) -> str ("Subject: ..." + body). Reads the roster module directly, so no roster argument. Never asks the client about headcount; the owner approves before sending.
- .env.example: COMPANY_NAME, ROLE added.
Needs from B: send_email(to, subject, body) in integrations/ for the recruit's contract (SMTP or a print-to-terminal fallback is fine for the demo); send_buttons for "I agree".
Blocked on: nothing.

## 13 Nov — Agent A (Max)
Done: agent/roster.py on branch max/roster (built on max/replies). Module-level state, saved to data/state.json.
- add_shifts(shifts), add_cleaners(cleaners), mark_asked(cleaner_id, shift_ids)
- apply(reply) -> list[str] (readable notes; also stores reply constraints on the cleaner)
- agree(cleaner_id, shift_id), cancel(cleaner_id, shift_id)
- open_shifts() -> list[Shift], is_full(shift_id), asked_before(shift_id) -> set[str] (for re-staffing), summary() -> str
- save(), load()
Unknown headcount counts as open until the owner sets it.
Needs from B: nothing.
Blocked on: nothing.

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
