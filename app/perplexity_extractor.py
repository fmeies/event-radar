from typing import Optional

import httpx

from .claude_extractor import _parse_json, _sites_hint
from .config import settings
from .logger import get_logger

log = get_logger("sonar")

_API_URL = "https://api.perplexity.ai/chat/completions"

_SYSTEM = """\
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


def _user_message(term: str, location: str, year: int, user_sites: list[str]) -> str:
    return (
        f"Search for upcoming public events and appearances by {term} in {location} in {year}."
        f" Include concerts, readings, lectures, talks, and signings."
        f"{_sites_hint(user_sites)} Return ONLY a JSON array with the events you find."
    )


async def search_events(
    term: str, location: str, year: int, user_sites: Optional[list[str]] = None
) -> list[dict]:
    label = f"{term} in {location} {year}"
    log.info("Perplexity Sonar search: '%s'", label)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                _API_URL,
                headers={
                    "Authorization": f"Bearer {settings.perplexity_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "sonar",
                    "messages": [
                        {"role": "system", "content": _SYSTEM},
                        {
                            "role": "user",
                            "content": _user_message(
                                term, location, year, user_sites or []
                            ),
                        },
                    ],
                    "max_tokens": 1024,
                },
            )
            r.raise_for_status()
    except Exception as exc:
        log.error("Perplexity API call failed for '%s': %s", label, exc, exc_info=True)
        return []

    raw = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    if not raw:
        log.warning("Empty response from Perplexity for '%s'", label)
        return []

    log.debug("Perplexity response for '%s': %s", label, raw[:500])
    return _parse_json(raw, label)
