"""One function to call the language model and get JSON back.

Featherless exposes an OpenAI-compatible API, so we use the OpenAI client.
Settings come from .env: FEATHERLESS_API_KEY, FEATHERLESS_BASE_URL, FEATHERLESS_MODEL.
"""
import json
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

JSON_RULE = "Reply with one valid JSON object only. No prose, no markdown fences."
TIMEOUT_SECONDS = 150   # a full answer takes about 1 minute at ~17 tokens/s
MAX_TOKENS = 2000       # stops a model that keeps repeating itself

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.environ["FEATHERLESS_API_KEY"],
            base_url=os.getenv("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1"),
            timeout=TIMEOUT_SECONDS,
            max_retries=0,  # chat_json does its own single retry
        )
    return _client


def _parse(text: str) -> dict:
    """Parse the model's reply, tolerating ``` fences and text around the object."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError(f"no JSON object in reply: {text[:200]!r}")
    result = json.loads(text[start : end + 1])
    if not isinstance(result, dict):
        raise ValueError("reply is JSON but not an object")
    return result


def chat_json(system: str, user: str) -> dict:
    """Send one system + user message and return the reply as a dict.

    Retries once if the reply is empty, cut off or not valid JSON, then raises
    ValueError. Each request times out after TIMEOUT_SECONDS, so the worst case
    is two timeouts.
    """
    messages = [
        {"role": "system", "content": f"{system}\n\n{JSON_RULE}"},
        {"role": "user", "content": user},
    ]
    last_error: Exception | None = None
    for _ in range(2):
        response = _get_client().chat.completions.create(
            model=os.environ["FEATHERLESS_MODEL"],
            messages=messages,
            temperature=0,
            max_tokens=MAX_TOKENS,
        )
        if not response.choices:  # Featherless sometimes returns an empty body
            last_error = ValueError(f"empty response: {response.model_dump_json()[:300]}")
            continue
        reply = response.choices[0].message.content or ""
        if response.choices[0].finish_reason == "length":
            last_error = ValueError(f"reply cut off at {MAX_TOKENS} tokens")
            continue
        try:
            return _parse(reply)
        except (ValueError, json.JSONDecodeError) as error:
            last_error = error
            messages += [
                {"role": "assistant", "content": reply},
                {"role": "user", "content": f"That was not valid JSON ({error}). {JSON_RULE}"},
            ]
    raise ValueError(f"model did not return valid JSON after a retry: {last_error}")


if __name__ == "__main__":
    print(chat_json("You are a test.", 'Return {"ok": true, "city": "Prague"}.'))
