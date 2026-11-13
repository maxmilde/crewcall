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
Done: shared/schemas.py draft on branch max/schemas (not merged): Cleaner, Request, Shift, OpenQuestion, Outreach, Reply, RosterEntry, Candidate as dataclasses. Conventions under "Schema conventions" in the doc. Shift.hours_confirmed defaults to False (set True only when the request states final hours). Added empty shared/__init__.py.
Needs from B: review schemas.py, especially Cleaner (Telegram fields may change once your bot design is clear) and Candidate. Then the humans freeze it.
Blocked on: nothing.
