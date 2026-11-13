# CrewCall

An AI staffing agent for a small cleaning business. The owner gets client requests by email and staffs every one by hand from a pool of about 50 cleaners: calling and texting people one by one, repeating the same details, and tracking who said yes. CrewCall takes a request from email to a confirmed crew, while the owner keeps every decision that matters.

## What it does

1. **Reads the client's email** (messy, real wording) into shifts: dates, alternative dates, hours, headcount, tasks. Anything missing becomes a question for the owner; nothing is guessed.
2. **The owner approves** the shifts and decides the headcount.
3. **Asks the nearest cleaners first.** Apify computes public-transport times from every cleaner to the site; for N people it asks the 2N nearest. Each offer says how far it is ("about 25 min from you").
4. **Understands free-text replies** on Telegram ("only Thursday", "too far for me") and fills the roster. The first N yeses are confirmed, later ones go on standby.
5. **Sends an assignment confirmation** with an "I agree" button.
6. **Decides what to do with open shifts:** ask more people, draft a Facebook post in the owner's own style, or hand it to the owner.
7. **Screens new applicants** who message the bot from that post, and sends approved ones a work contract by email.
8. **Re-staffs cancellations** on its own: standby first, then the next nearest.
9. **Drafts the reply to the client.** The owner sends it; the agent never contacts the client.

It also **remembers** each cleaner: "never weekends" or "30 minutes max, I live in Libeň" are saved and respected next time. And the owner can just talk to it: "who's on Friday?", "add one more person Thursday".

## Guardrails

The workflow is a fixed sequence. The model only chooses among allowed moves at a few decision points, and code checks every choice. The agent never contacts the client, never changes headcount, pay or shift details, and only messages people it selected. Anything for a new person or the client goes through the owner.

## Not just cleaning

Everything specific to the line of work lives in `data/domains/<name>.json`. `DOMAIN=events` turns the same agent into an event-staffing assistant. The pattern fits anyone coordinating people by phone: volunteers, events, home care.

## Built with

- **Featherless** (`deepseek-ai/DeepSeek-V4.1-Flash`): reading emails and replies, writing messages, decisions
- **Apify**: public-transport travel times (Google Maps directions Actor)
- **Telegram**: the channel for the owner, cleaners and applicants
- Python 3.11, plain functions and dataclasses

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # add FEATHERLESS_API_KEY (and APIFY_TOKEN, TELEGRAM_BOT_TOKEN for the live version)

.venv/bin/python -m agent.intake data/requests/email3.txt   # one email -> shifts and questions
.venv/bin/python -m agent.simulate                          # the whole flow in the terminal, simulated cleaners
```

## Layout

| Path | What |
|---|---|
| `agent/workflow.py` | The workflow and its decision points |
| `agent/intake.py`, `replies.py`, `outreach.py` | Reading emails and replies, writing offers and the Facebook post |
| `agent/roster.py` | Who is on which shift (saved to `data/state.json`) |
| `agent/owner_chat.py`, `applicants.py` | Owner commands, applicant screening |
| `agent/documents.py`, `client_reply.py` | Simulated work contract and assignment, client reply draft |
| `integrations/` | Telegram bot, Apify runs |
| `shared/` | Data models and the model client |
| `data/requests/` | Real client emails, anonymised |

The work contract and assignment confirmation are simulated documents, marked SAMPLE.
