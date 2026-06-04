from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import date, datetime, timezone

import httpx
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .claude_extractor import discover_sites, extract_events, search_and_extract_events
from .config import settings
from .constants import MAX_SEARCH_SITES
from .database import SessionLocal
from .email_service import send_event_notification
from .logger import get_logger
from .models import SeenEvent, User

log = get_logger("pipeline")

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"


def _is_valid_event(event: dict, location: str) -> bool:
    """Returns True only for events with a clean future date in the user's city."""
    date_str = event.get("date")
    city = event.get("city")

    if not date_str or not city:
        return False

    try:
        event_date = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return False

    if event_date < date.today():
        return False

    return location.lower() in city.lower() or city.lower() in location.lower()


_STREAMED_LOGGERS = ("pipeline", "claude", "email")
_user_locks: dict[int, asyncio.Lock] = {}
_INTER_TERM_DELAY_SECONDS = 15
_INTER_DISCOVERY_DELAY_SECONDS = 5


class _QueueLogHandler(logging.Handler):
    """Captures log records from app loggers into an asyncio.Queue for SSE streaming."""

    def __init__(self, queue: asyncio.Queue) -> None:
        super().__init__()
        self.queue = queue
        self.setFormatter(logging.Formatter("%(levelname)-8s  %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.queue.put_nowait(self.format(record))
        except Exception:
            pass


def _event_hash(user_id: int, event: dict) -> str:
    raw = f"{user_id}:{event.get('name', '')}:{event.get('date', '')}:{event.get('venue', '')}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def _brave_search(query: str) -> list[dict]:
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": settings.brave_api_key,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.get(
                BRAVE_URL, headers=headers, params={"q": query, "count": 10}
            )
            r.raise_for_status()
            results = r.json().get("web", {}).get("results", [])
            log.debug("Brave raw results for '%s': %d hits", query, len(results))
            for i, result in enumerate(results):
                log.debug(
                    "  [%d] %s — %s",
                    i + 1,
                    result.get("title", ""),
                    result.get("url", ""),
                )
            return results
        except Exception as exc:
            log.warning("Brave search failed for '%s': %s", query, exc)
            return []


async def _brave_search_and_extract(query: str, user_sites: list[str]) -> list[dict]:
    results = await _brave_search(query)
    if not results:
        log.info("Brave returned 0 results for '%s'", query)
        return []
    log.info("Brave returned %d result(s) for '%s'", len(results), query)
    snippets = "\n\n---\n\n".join(
        f"URL: {r.get('url', '')}\nTitle: {r.get('title', '')}\nSnippet: {r.get('description', '')}"
        for r in results
    )
    events = await extract_events(snippets, query, user_sites)
    log.info("Brave+Claude extracted %d event(s) for '%s'", len(events), query)
    for event in events:
        log.debug(
            "  Event: %s | %s | %s",
            event.get("name"),
            event.get("date"),
            event.get("venue"),
        )
    return events


async def _search_events(
    term: str, location: str, year: int, user_sites: list[str]
) -> list[dict]:
    if settings.search_mode != "claude":
        return await _brave_search_and_extract(f"{term} {location} {year}", user_sites)
    events = await search_and_extract_events(term, location, year, user_sites)
    if not events and settings.brave_api_key:
        log.info(
            "Claude found nothing, falling back to Brave for '%s %s'", term, location
        )
        events = await _brave_search_and_extract(
            f"{term} {location} {year}", user_sites
        )
    return events


async def _process_user(user: User, db) -> None:
    if not user.location:
        log.info("Skipping %s — no location set", user.email)
        return
    if not user.search_terms:
        log.info("Skipping %s — no search terms", user.email)
        return

    year = datetime.now().year
    new_events: list[dict] = []
    user_sites = [s.site for s in user.search_sites]

    for i, term in enumerate(user.search_terms):
        if i > 0:
            await asyncio.sleep(_INTER_TERM_DELAY_SECONDS)
        events = await _search_events(term.term, user.location, year, user_sites)

        for event in events:
            if not _is_valid_event(event, user.location):
                log.debug(
                    "Filtered out: %s | date=%s city=%s",
                    event.get("name"),
                    event.get("date"),
                    event.get("city"),
                )
                continue

            h = _event_hash(user.id, event)
            already_seen = (
                db.query(SeenEvent)
                .filter(SeenEvent.user_id == user.id, SeenEvent.event_hash == h)
                .first()
            )
            if already_seen:
                log.debug("Already seen: %s (%s)", event.get("name"), event.get("date"))
            else:
                log.info(
                    "New event: %s | %s | %s",
                    event.get("name"),
                    event.get("date"),
                    event.get("venue"),
                )
                new_events.append(event)
                db.execute(
                    sqlite_insert(SeenEvent)
                    .values(
                        user_id=user.id,
                        event_hash=h,
                        created_at=datetime.now(timezone.utc),
                    )
                    .on_conflict_do_nothing()
                )

    db.commit()

    if new_events:
        await send_event_notification(user.email, new_events, user.location)
        log.info("%d new event(s) sent to %s", len(new_events), user.email)
    else:
        log.info("No new events for %s", user.email)


async def run_pipeline() -> None:
    db = SessionLocal()
    try:
        users = db.query(User).filter(User.is_verified.is_(True)).all()
        log.info("Starting pipeline for %d user(s)", len(users))
        for user in users:
            try:
                log.info(
                    "Processing %s (location: %s, terms: %d)",
                    user.email,
                    user.location,
                    len(user.search_terms),
                )
                await _process_user(user, db)
            except Exception as exc:
                log.error("Failed for %s: %s", user.email, exc, exc_info=True)
    finally:
        db.close()


async def _run_for_user(user_id: int) -> None:
    if user_id not in _user_locks:
        _user_locks[user_id] = asyncio.Lock()
    lock = _user_locks[user_id]

    if lock.locked():
        log.info(
            "Pipeline already running for user %d, skipping duplicate run", user_id
        )
        return

    async with lock:
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                log.info("Manual pipeline run for %s", user.email)
                await _process_user(user, db)
        finally:
            db.close()


async def _collect_sites_for_user(user: User) -> list[dict]:
    """Discover sites for all search terms. Returns list of {site, term} dicts — no DB writes."""
    if not user.search_terms:
        log.info("No search terms for %s, skipping discovery", user.email)
        return []

    seen: set[str] = set()
    results: list[dict] = []

    for i, term in enumerate(user.search_terms):
        if len(results) >= MAX_SEARCH_SITES:
            log.info("Site limit (%d) reached, stopping discovery", MAX_SEARCH_SITES)
            break
        if i > 0:
            await asyncio.sleep(_INTER_DISCOVERY_DELAY_SECONDS)

        for raw_site in await discover_sites(term.term):
            site = (
                raw_site.strip()
                .lower()
                .removeprefix("https://")
                .removeprefix("http://")
                .rstrip("/")
            )
            if not site or site in seen or len(results) >= MAX_SEARCH_SITES:
                continue
            seen.add(site)
            results.append({"site": site, "term": term.term})

    log.info("Discovery complete — %d site(s) found", len(results))
    return results


async def run_discovery_for_user_streamed(user_id: int):
    """Yields log lines, then a final {"type":"result","sites":[...]} object for SSE streaming."""
    if user_id not in _user_locks:
        _user_locks[user_id] = asyncio.Lock()

    if _user_locks[user_id].locked():
        yield "INFO      Pipeline is already running — please wait."
        return

    queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=200)
    handler = _QueueLogHandler(queue)
    discovered: list[dict] = []

    for name in _STREAMED_LOGGERS:
        logging.getLogger(name).addHandler(handler)

    async def _run() -> None:
        try:
            async with _user_locks[user_id]:
                db = SessionLocal()
                try:
                    user = db.query(User).filter(User.id == user_id).first()
                    if user:
                        log.info("Starting site discovery for %s", user.email)
                        discovered.extend(await _collect_sites_for_user(user))
                finally:
                    db.close()
        except Exception as exc:
            log.error("Discovery failed: %s", exc, exc_info=True)
        finally:
            for name in _STREAMED_LOGGERS:
                logging.getLogger(name).removeHandler(handler)
            await queue.put(None)

    asyncio.create_task(_run())

    while True:
        msg = await queue.get()
        if msg is None:
            break
        yield msg

    yield {"type": "result", "sites": discovered}


async def run_for_user_streamed(user_id: int):
    """Async generator that runs the pipeline and yields log lines for SSE streaming."""
    if user_id not in _user_locks:
        _user_locks[user_id] = asyncio.Lock()

    if _user_locks[user_id].locked():
        yield "INFO      Pipeline is already running — please wait."
        return

    queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=500)
    handler = _QueueLogHandler(queue)

    for name in _STREAMED_LOGGERS:
        logging.getLogger(name).addHandler(handler)

    async def _run() -> None:
        try:
            await _run_for_user(user_id)
        finally:
            for name in _STREAMED_LOGGERS:
                logging.getLogger(name).removeHandler(handler)
            await queue.put(None)

    asyncio.create_task(_run())

    while True:
        msg = await queue.get()
        if msg is None:
            break
        yield msg
