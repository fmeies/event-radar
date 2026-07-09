"""Shared prompts, parsers, and helpers used by all search extractors."""

import json
import re
from typing import Optional

from .constants import MAX_SEARCH_SITES
from .logger import get_logger

log = get_logger("extract")

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
CRITICAL: Only include events for the exact person or group named in the search term.
Match the full name, not just the surname — "Norbert Waltz" must never return events
for "Sasha Waltz". When in doubt, leave the event out.
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


def _find_events_array(text: str) -> Optional[list[dict]]:
    """Return the first JSON array of objects embedded in `text`, or None.

    The model is asked for a bare JSON array, but — especially via Claude web
    search — it often wraps it in prose ("I found one event:"), code fences, or
    a trailing "Note: ...", and sometimes emits citation markers like ``[1]``
    before the real payload. A single ``json.loads`` of the whole string fails on
    all of these ("Extra data"). Scanning every ``[`` with a raw decoder, which
    stops after one value and ignores trailing text, tolerates them instead.

    Returns ``[]`` when the model validly reported no events, and ``None`` only
    when a ``[`` was present but nothing decoded to a valid array (malformed or
    truncated output) — the one case worth a warning.
    """
    decoder = json.JSONDecoder()
    saw_bracket = False
    saw_valid_array = False
    for match in re.finditer(r"\[", text):
        saw_bracket = True
        try:
            value, _ = decoder.raw_decode(text, match.start())
        except json.JSONDecodeError:
            continue
        if not isinstance(value, list):
            continue
        saw_valid_array = True
        events = [item for item in value if isinstance(item, dict)]
        if events:
            return events
    if saw_bracket and not saw_valid_array:
        return None
    return []


def parse_json(raw: str, context: str) -> list[dict]:
    events = _find_events_array(raw)
    if events is None:
        log.warning("Failed to parse response for '%s': %s", context, raw[:200])
        return []
    return events
