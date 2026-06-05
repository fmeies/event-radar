import json
from typing import Optional

import anthropic
from anthropic.types import TextBlock

from .config import settings
from .logger import get_logger
from .prompts import SYSTEM_SEARCH, parse_json, search_user_message, sites_hint

log = get_logger("claude")

_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

_MODEL = "claude-haiku-4-5-20251001"
_MAX_SNIPPET_CHARS = 8000

_SYSTEM_BRAVE = """\
You extract structured event data from web search result snippets.
Events include concerts, readings, lectures, talks, signings, and any other public appearances.
Return exclusively a JSON array. Each object contains:
- "name": artist, band, author, or speaker name (string)
- "date": event date, ISO format preferred (string or null)
- "venue": venue or hall name (string or null)
- "city": city (string or null)
- "url": direct URL to the event or ticket page (string or null)

Only include events that are thematically relevant to the search term.
If no events are recognisable, return [].
No markdown, no comments — only the JSON array."""

_SYSTEM_DISCOVER = """\
You find the best websites to search for upcoming public events and appearances by a given person or group.
Events include concerts, readings, lectures, talks, signings, and other public appearances.
CRITICAL: Respond with a valid JSON array only — no explanations, no prose, no markdown.
Format: ["domain1.com", "domain2.com"] or [] if nothing found.
Include the person's official website and at most 2–3 relevant event-listing or ticketing sites.
Maximum 5 domains total. Unknown persons → return [].
Any response that is not a JSON array is wrong."""


def _user_message_brave(query: str, snippets: str, user_sites: list[str]) -> str:
    return (
        f"Search term: {query}{sites_hint(user_sites)}"
        f"\n\nSearch results:\n{snippets[:_MAX_SNIPPET_CHARS]}"
    )


async def extract_events(
    snippets: str, query: str, user_sites: Optional[list[str]] = None
) -> list[dict]:
    """Extract events from Brave search snippets."""
    log.debug(
        "Calling Claude for query '%s' (%d chars of snippets)", query, len(snippets)
    )
    try:
        response = await _client.messages.create(
            model=_MODEL,
            max_tokens=1024,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_BRAVE,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": _user_message_brave(query, snippets, user_sites or []),
                }
            ],
        )
    except Exception as exc:
        log.error("Claude API call failed for '%s': %s", query, exc, exc_info=True)
        return []

    raw = next((b.text for b in response.content if isinstance(b, TextBlock)), "")
    log.debug("Claude raw response for '%s': %s", query, raw[:500])
    return parse_json(raw, query)


async def search_and_extract_events(
    term: str, location: str, year: int, user_sites: Optional[list[str]] = None
) -> list[dict]:
    """Use Claude's built-in web search to find and extract events directly."""
    label = f"{term} in {location} {year}"
    log.info("Claude web search: '%s'", label)
    try:
        response = await _client.messages.create(
            model=_MODEL,
            max_tokens=1024,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_SEARCH,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": search_user_message(term, location, year, user_sites),
                }
            ],
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
    return parse_json(raw, label)


async def discover_sites(term: str) -> list[str]:
    """Use Claude web search to find the best websites for concert info about an artist."""
    log.info("Discovering sites for '%s'", term)
    try:
        response = await _client.messages.create(
            model=_MODEL,
            max_tokens=512,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_DISCOVER,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": f"Find the best websites for upcoming public events and appearances by: {term}",
                }
            ],
        )
    except Exception as exc:
        log.error("Site discovery failed for '%s': %s", term, exc, exc_info=True)
        return []

    raw = next(
        (b.text for b in reversed(response.content) if isinstance(b, TextBlock)), ""
    )
    if not raw:
        log.debug("No response from Claude for site discovery of '%s'", term)
        return []

    raw = raw.strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        log.debug("No sites found for '%s' (model returned natural language)", term)
        return []

    sites = [s for s in result if isinstance(s, str)]
    if sites:
        log.info("Discovered %d site(s) for '%s': %s", len(sites), term, sites)
    else:
        log.info("No sites found for '%s'", term)
    return sites
