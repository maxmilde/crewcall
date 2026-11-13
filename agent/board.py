"""Live board for the projector: roster per client, the agent's decisions, counters.

Run: .venv/bin/python -m agent.board   then open http://localhost:8000
It only reads data/state.json and data/events.jsonl, so it shows whatever the agent is doing.
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from agent.describe import when, where
from agent.events import EVENTS_FILE
from agent.roster import STATE_FILE
from shared.schemas import Shift

PAGE = (Path(__file__).parent / "board.html").read_text()
CALLS_PER_PERSON = 3  # rough: calls/texts it takes by hand to fill one place


def snapshot() -> dict:
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {"shifts": [], "cleaners": [], "entries": []}
    names = {c["id"]: c["name"] for c in state["cleaners"]}
    lines = EVENTS_FILE.read_text().splitlines() if EVENTS_FILE.exists() else []
    events = [json.loads(line) for line in lines if line.strip()]
    clients: dict[str, list] = {}
    for raw in state["shifts"]:
        shift = Shift(**raw)
        mine = [e for e in state["entries"] if e["shift_id"] == shift.id]
        def people(status):
            return [{"name": names.get(e["cleaner_id"], e["cleaner_id"]), "agreed": bool(e.get("agreed_at"))}
                    for e in mine if e["status"] == status]
        clients.setdefault(shift.request_id, []).append({
            "id": shift.id, "when": when(shift), "where": where(shift), "task": shift.task_summary,
            "need": shift.headcount, "confirmed": people("confirmed"), "waiting": people("asked"),
            "standby": people("standby"),
        })
    needed = sum(s["headcount"] or 0 for s in state["shifts"])
    count = lambda kind: sum(1 for e in events if e["kind"] == kind)
    return {
        "clients": clients,
        "events": events[-14:][::-1],
        "counters": {
            "shifts": len(state["shifts"]), "needed": needed,
            "filled": sum(1 for e in state["entries"] if e["status"] == "confirmed"),
            "offers": count("offer"), "replies": count("reply"), "owner": count("owner"),
            "calls": needed * CALLS_PER_PERSON,
        },
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body, kind = (json.dumps(snapshot(), ensure_ascii=False), "application/json") if self.path == "/data" else (PAGE, "text/html")
        data = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", f"{kind}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # keep the terminal quiet
        pass


if __name__ == "__main__":
    print("Board on http://localhost:8000")
    ThreadingHTTPServer(("", 8000), Handler).serve_forever()
