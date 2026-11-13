# Demo script (target 2:45, hard stop 3:00)

## Setup before going on stage
- Zahid's laptop runs `python -m integrations.run_bot`; terminal shows `[inbox] watching ...`.
- Zahid's phone is the owner, mirrored on the projector.
- Cleaners: Max's phone + 3 friends' phones, all linked (owner: "add <name>, <area>", they tap the link).
- Applicant: a 5th phone, NOT linked.
- The client email (below) is ready in Max's mail app, not sent yet. Send it from an account with a client-like name.

## Timeline
| Time | Action | Owner screen (projector) | We say |
|---|---|---|---|
| 0:00–0:15 | — | empty chat | "A friend's mum runs a cleaning business: 50 cleaners, every request staffed by phone, one by one." |
| 0:15–0:40 | Max sends the email | 📩 client, location, shifts, headcount, open points | "A client emails her work inbox. The AI reads it: dates, hours, people, and what's still unclear." |
| 0:40–0:50 | Owner: "yes" | 📋 job card 0/2 · 0/1 | "Nothing goes out until she says yes." |
| 0:50–1:20 | Phones buzz. Max: "only Thursday". Friend: "too far" | card updates live | "Nearest first, by real transit time from Apify. It understands free text and asks the 'too far' person their limit." |
| 1:20–1:35 | Max taps **I agree** | card: Max ✍️ | "Confirmed in one tap." |
| 1:35–1:55 | Friday still open | 🟠 + 🤔 reason → 📣 Facebook post with bot link | "It decides on its own: nobody's left, so it writes her usual Facebook post." |
| 1:55–2:15 | 5th phone opens the link and applies | 🙋 applicant → owner "yes" → contract emailed | "New people apply through the bot. She approves; the contract goes out by email." |
| 2:15–2:30 | Max: "sorry, I'm sick, can't come" | ⚠️ cancelled → standby moved in | "Cancellations fix themselves." |
| 2:30–2:45 | Job full | ✅ + client draft → owner "send" → 📨 | "It drafts the reply to the client. What took her an afternoon of calls now takes minutes." |

Cut first if long: the applicant step.

## The email
Subject: Cleaning staff for our event

Hello,
we are hosting a company event at our office in Karlín and need cleaning staff:
- 2 cleaners on Thursday 19/11 from 16:00 to 20:00
- 1 cleaner on Friday 20/11 from 08:00 to 12:00 for the clean-up
Please let us know who you can send.
Best regards,
Petra Nováková, Event Office
