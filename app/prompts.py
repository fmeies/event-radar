"""Shared prompts, parsers, and helpers used by all search extractors."""

import json
import re
from typing import Optional

from .constants import MAX_SEARCH_SITES
from .logger import get_logger

log = get_logger("extract")

_FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)

SYSTEM_SEARCH = """\
You search for upcoming public events and appearances and return structured data.
Events include concerts, readings, lectures, talks, signings, and any other public appearances.
Return exclusively a JSON array. Each object contains:
- "name": artist, band, author, or speaker name (string)
- "date": event date, ISO format YYYY-MM-DD (string or null)
- "venue": venue or hall name (string or null)
- "city": city (string or null)
- "url": direct URL to the event or ticket page (string or null)

Only include confirmed upcoming events with a known date and city.
If no events are found, return [].
No markdown, no comments — only the JSON array."""


def sites_hint(user_sites: list[str]) -> str:
    if not user_sites:
        return ""
    return " Prefer results from: " + ", ".join(user_sites[:MAX_SEARCH_SITES]) + "."


def search_user_message(
    term: str, location: str, year: int, user_sites: Optional[list[str]] = None
) -> str:
    return (
        f"Search for upcoming public events and appearances by {term} in {location} in {year}."
        f" Include concerts, readings, lectures, talks, and signings."
        f"{sites_hint(user_sites or [])} Return ONLY a JSON array with the events you find."
    )


def parse_json(raw: str, context: str) -> list[dict]:
    candidate = raw.strip()
    fenced = _FENCE_RE.search(candidate)
    if fenced:
        candidate = fenced.group(1).strip()
    elif not candidate.startswith(("[", "{")):
        m = re.search(r"[\[{]", candidate)
        if m:
            candidate = candidate[m.start() :]
    try:
        result = json.loads(candidate)
    except json.JSONDecodeError as exc:
        log.warning(
            "Failed to parse response for '%s': %s | %s", context, exc, raw[:200]
        )
        return []

    if not isinstance(result, list):
        log.warning(
            "Expected a JSON array for '%s', got %s", context, type(result).__name__
        )
        return []
    return result
