"""Public-transport travel time from each cleaner's area to a site, via Apify.

One matrix run of rastriq/google-maps-directions-traffic (transit, arrive by the
shift start). Results are cached per origin/site/time in data/cache/travel.json,
so reruns are instant and free; only new pairs go to Apify. If Apify fails, the
stand-in's fake times are used so the demo keeps going.
"""
import json
import os
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

from agent import stand_ins
from shared.schemas import Cleaner

load_dotenv()

ACTOR = "rastriq~google-maps-directions-traffic"
CACHE_FILE = Path("data/cache/travel.json")


def _place(text: str) -> str:
    """Add the city so Google finds "Žižkov" in Prague, not somewhere else."""
    city = os.getenv("CITY", "Prague")
    return text if city.lower() in text.lower() else f"{text}, {city}"


def _run(origins: list[str], destination: str, day: str, time: str) -> list[dict]:
    payload = {
        "origins": origins, "destinations": [destination], "travelModes": ["transit"],
        "timeMode": "arrive_by", "travelDate": day or "1 day", "travelTime": time,
        "maxRoutes": 1, "includeSteps": False, "includePolyline": False,
    }
    url = (f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items"
           f"?token={os.environ['APIFY_TOKEN']}&timeout=180")
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=200) as resp:
        return json.load(resp)


def travel_minutes(cleaners: list[Cleaner], address: str, arrive_by: str) -> dict[str, int]:
    """{cleaner_id: minutes by public transport}, arriving by arrive_by ("YYYY-MM-DDTHH:MM").
    Cleaners without an area, or with no transit route, are left out."""
    if not address:
        return {}
    day, _, time = arrive_by.partition("T")
    destination = _place(address)
    origin = {c.id: _place(c.home_area) for c in cleaners if c.home_area}
    key = lambda o: f"{o}|{destination}|{day}T{time}"

    cache = json.loads(CACHE_FILE.read_text()) if CACHE_FILE.exists() else {}
    missing = sorted({o for o in origin.values() if key(o) not in cache})
    if missing:
        try:
            for item in _run(missing, destination, day, time or "09:00"):
                o = missing[item["matrixOriginIndex"]]
                ok = item.get("status") == "OK" and item.get("durationSeconds")
                cache[key(o)] = round(item["durationSeconds"] / 60) if ok else None
        except Exception as error:  # no token, network, Apify down: fall back, don't stop the demo
            print(f"  [apify] travel times failed ({type(error).__name__}: {error}); using estimates")
            return stand_ins.travel_minutes(cleaners, address, arrive_by)
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(cache, indent=1, ensure_ascii=False))
    return {cid: cache[key(o)] for cid, o in origin.items() if cache.get(key(o)) is not None}
