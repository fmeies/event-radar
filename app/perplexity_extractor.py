from typing import Optional

import httpx

from .config import settings
from .logger import get_logger
from .prompts import SYSTEM_SEARCH, parse_json, search_user_message

log = get_logger("sonar")

_API_URL = "https://api.perplexity.ai/chat/completions"


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
                    "model": settings.perplexity_model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_SEARCH},
                        {
                            "role": "user",
                            "content": search_user_message(
                                term, location, year, user_sites
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
    return parse_json(raw, label)
