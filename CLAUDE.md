# CLAUDE.md

Source of truth: the project doc, https://claude.ai/artifact/YQaXgwLfsfgt8KWv6bbVAr
Read all of it, every section, at the start of every session. Never copy it into the repo. If anything disagrees with it, the doc wins.

## Who you are
Set in CLAUDE.local.md (not committed): "You are Agent A (Max)" or "You are Agent B (Zahid)".

## Ownership
- Agent A (Max): shared/llm.py, agent/intake.py, agent/outreach.py, agent/replies.py, agent/roster.py
- Agent B (Zahid): integrations/, agent/matching.py, agent/recruit.py
- Both, worked on together: demo/
- Both, agreed by the humans and then frozen: shared/schemas.py
- data/: add files freely, don't edit the other agent's files
Never edit files you don't own. If you need a change there, write a request in HANDOFF.md.

Never edit the project doc. Propose changes in HANDOFF.md; a human updates the doc.

## Every session
1. git pull origin main into your branch.
2. Read the whole project doc, then HANDOFF.md.
3. Work on your next step in the Build order section.
4. When that step's "Done when" test passes: commit, push, add a note at the top of HANDOFF.md.

## When something is unclear
1. Check the project doc.
2. If the choice only affects your own folder: pick the simplest option that keeps the demo working and note it in HANDOFF.md.
3. If it touches shared/, the other agent's folder or the demo story: stop and ask your human.
Never invent requirements.

## Code rules
- Python 3.11, plain functions and dataclasses, type hints, short files.
- Secrets only in .env; keep .env.example up to date.
- Cache Apify results in data/cache/.
- New dependency: add it to requirements.txt and mention it in HANDOFF.md.
- Working and simple beats clever.

## Git
Branches max/<task> and zahid/<task>. Never commit to main, never force-push. Humans merge.
