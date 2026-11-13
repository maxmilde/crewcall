"""Everything specific to one line of work, so the same agent can staff other domains.

DOMAIN in .env picks data/domains/<name>.json (default: cleaning).
Prompts and templates use {{key}} placeholders that are filled from that file.
"""
import json
import os
from functools import cache
from pathlib import Path

ROOT = Path(__file__).parent.parent


@cache
def settings() -> dict:
    name = os.getenv("DOMAIN", "cleaning")
    data = json.loads((ROOT / "data" / "domains" / f"{name}.json").read_text())
    data["pay_text"] = os.getenv("PAY_TEXT") or data["pay_text"]
    return data


def fill(text: str) -> str:
    for key, value in settings().items():
        text = text.replace("{{" + key + "}}", value)
    return text


def prompt(name: str) -> str:
    return fill((ROOT / "agent" / "prompts" / f"{name}.txt").read_text())
