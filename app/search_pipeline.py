from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import date, datetime, timezone

import httpx
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .claude_extractor import extract_events, search_and_extract_events
from .config import settings
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
            r = await client.get(BRAVE_URL, headers=headers, params={"q": query, "count": 10})
            r.raise_for_status()
            results = r.json().get("web", {}).get("results", [])
            log.debug("Brave raw results for '%s': %d hits", query, len(results))
            for i, result in enumerate(results):
                log.debug("  [%d] %s — %s", i + 1, result.get("title", ""), result.get("url", ""))
            return results
        except Exception as exc:
            log.warning("Brave search failed for '%s': %s", query, exc)
            return []


async def _brave_search_and_extract(query: str) -> list[dict]:
    results = await _brave_search(query)
    if not results:
        log.info("Brave returned 0 results for '%s'", query)
        return []
    log.info("Brave returned %d result(s) for '%s'", len(results), query)
    snippets = "\n\n---\n\n".join(
        f"URL: {r.get('url', '')}\nTitle: {r.get('title', '')}\nSnippet: {r.get('description', '')}"
        for r in results
    )
    events = await extract_events(snippets, query)
    log.info("Brave+Claude extracted %d event(s) for '%s'", len(events), query)
    for event in events:
        log.debug("  Event: %s | %s | %s", event.get("name"), event.get("date"), event.get("venue"))
    return events


async def _search_events(term: str, location: str, year: int) -> list[dict]:
    if settings.search_mode != "claude":
        return await _brave_search_and_extract(f"{term} {location} {year}")
    events = await search_and_extract_events(term, location, year)
    if not events and settings.brave_api_key:
        log.info("Claude found nothing, falling back to Brave for '%s %s'", term, location)
        events = await _brave_search_and_extract(f"{term} {location} {year}")
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

    for term in user.search_terms:
        events = await _search_events(term.term, user.location, year)

        for event in events:
            if not _is_valid_event(event, user.location):
                log.debug("Filtered out: %s | date=%s city=%s", event.get("name"), event.get("date"), event.get("city"))
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
                log.info("New event: %s | %s | %s", event.get("name"), event.get("date"), event.get("venue"))
                new_events.append(event)
                db.execute(
                    sqlite_insert(SeenEvent).values(
                        user_id=user.id,
                        event_hash=h,
                        created_at=datetime.now(timezone.utc),
                    ).on_conflict_do_nothing()
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
                log.info("Processing %s (location: %s, terms: %d)", user.email, user.location, len(user.search_terms))
                await _process_user(user, db)
            except Exception as exc:
                log.error("Failed for %s: %s", user.email, exc, exc_info=True)
    finally:
        db.close()


async def run_for_user(user_id: int) -> None:
    if user_id not in _user_locks:
        _user_locks[user_id] = asyncio.Lock()
    lock = _user_locks[user_id]

    if lock.locked():
        log.info("Pipeline already running for user %d, skipping duplicate run", user_id)
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
            await run_for_user(user_id)
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
