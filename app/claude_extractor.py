import json

import anthropic
from anthropic.types import TextBlock

from .config import settings
from .logger import get_logger

log = get_logger("claude")

_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

_SYSTEM = """\
You extract structured event data from web search result snippets.
Return exclusively a JSON array. Each object contains:
- "name": artist, band, or event name (string)
- "date": event date, ISO format preferred (string or null)
- "venue": venue or hall name (string or null)
- "city": city (string or null)
- "url": direct URL to the event or ticket page (string or null)

Only include events that are thematically relevant to the search term.
If no events are recognisable, return [].
No markdown, no comments — only the JSON array."""

_SYSTEM_SEARCH = """\
You search for upcoming live events and concerts and return structured data.
Return exclusively a JSON array. Each object contains:
- "name": artist, band, or event name (string)
- "date": event date, ISO format YYYY-MM-DD (string or null)
- "venue": venue or hall name (string or null)
- "city": city (string or null)
- "url": direct URL to the event or ticket page (string or null)

Only include confirmed upcoming events with a known date and city.
If no events are found, return [].
No markdown, no comments — only the JSON array."""


def _parse_json(raw: str, context: str) -> list[dict]:
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(lines[1:])
        if raw.endswith("```"):
            raw = raw[:-3].strip()
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, IndexError, AttributeError) as exc:
        log.warning(
            "Failed to parse Claude response for '%s': %s | %s", context, exc, raw[:200]
        )
        return []


_PROMPT_CACHE_HEADER = {"anthropic-beta": "prompt-caching-2024-07-31"}


async def extract_events(snippets: str, query: str) -> list[dict]:
    """Extract events from Brave search snippets."""
    log.debug(
        "Calling Claude for query '%s' (%d chars of snippets)", query, len(snippets)
    )
    try:
        response = await _client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": f"Search term: {query}\n\nSearch results:\n{snippets[:8000]}",
                }
            ],
            extra_headers=_PROMPT_CACHE_HEADER,
        )
    except Exception as exc:
        log.error("Claude API call failed for '%s': %s", query, exc, exc_info=True)
        return []

    raw = next((b.text for b in response.content if isinstance(b, TextBlock)), "")
    log.debug("Claude raw response for '%s': %s", query, raw[:500])
    return _parse_json(raw, query)


async def search_and_extract_events(term: str, location: str, year: int) -> list[dict]:
    """Use Claude's built-in web search to find and extract events directly."""
    label = f"{term} in {location} {year}"
    log.info("Claude web search: '%s'", label)
    try:
        response = await _client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_SEARCH,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Search for upcoming {term} concerts and live events in {location} in {year}. "
                        f"Return ONLY a JSON array with the events you find."
                    ),
                }
            ],
            extra_headers=_PROMPT_CACHE_HEADER,
        )
    except Exception as exc:
        log.error("Claude web search failed for '%s': %s", label, exc, exc_info=True)
        return []

    raw = next(
        (b.text for b in reversed(response.content) if isinstance(b, TextBlock)), ""
    )

    if not raw:
        log.warning("No text response from Claude web search for '%s'", label)
        return []

    log.debug("Claude web search response for '%s': %s", label, raw[:500])
    return _parse_json(raw, label)
