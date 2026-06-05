import logging

from datetime import date, timedelta

from app.search_pipeline import (
    _QueueLogHandler,
    _current_stream,
    _event_hash,
    _is_valid_event,
)

TOMORROW = (date.today() + timedelta(days=1)).isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()
TODAY = date.today().isoformat()


# ── _is_valid_event ────────────────────────────────────────────────────────────


def test_valid_event_passes():
    event = {"name": "Pixies", "date": TOMORROW, "city": "Berlin", "venue": "Zitadelle"}
    assert _is_valid_event(event, "Berlin") is True


def test_event_today_passes():
    event = {"name": "Pixies", "date": TODAY, "city": "Berlin", "venue": None}
    assert _is_valid_event(event, "Berlin") is True


def test_past_event_rejected():
    event = {"name": "Pixies", "date": YESTERDAY, "city": "Berlin", "venue": None}
    assert _is_valid_event(event, "Berlin") is False


def test_missing_date_rejected():
    event = {"name": "Pixies", "date": None, "city": "Berlin", "venue": None}
    assert _is_valid_event(event, "Berlin") is False


def test_missing_city_rejected():
    event = {"name": "Pixies", "date": TOMORROW, "city": None, "venue": "Zitadelle"}
    assert _is_valid_event(event, "Berlin") is False


def test_unparseable_date_rejected():
    event = {"name": "Pixies", "date": "Summer 2026", "city": "Berlin", "venue": None}
    assert _is_valid_event(event, "Berlin") is False


def test_wrong_city_rejected():
    event = {"name": "Pixies", "date": TOMORROW, "city": "Hamburg", "venue": None}
    assert _is_valid_event(event, "Berlin") is False


def test_city_substring_match():
    event = {
        "name": "Pixies",
        "date": TOMORROW,
        "city": "Berlin, Germany",
        "venue": None,
    }
    assert _is_valid_event(event, "Berlin") is True


def test_city_case_insensitive():
    event = {"name": "Pixies", "date": TOMORROW, "city": "berlin", "venue": None}
    assert _is_valid_event(event, "Berlin") is True


def test_date_with_time_component():
    event = {
        "name": "Pixies",
        "date": f"{TOMORROW}T20:00:00",
        "city": "Berlin",
        "venue": None,
    }
    assert _is_valid_event(event, "Berlin") is True


# ── _event_hash ────────────────────────────────────────────────────────────────


def test_hash_is_deterministic():
    event = {"name": "Nick Cave", "date": "2026-06-30", "venue": "Waldbühne"}
    assert _event_hash(1, event) == _event_hash(1, event)


def test_hash_differs_by_user():
    event = {"name": "Nick Cave", "date": "2026-06-30", "venue": "Waldbühne"}
    assert _event_hash(1, event) != _event_hash(2, event)


def test_hash_differs_by_event():
    e1 = {"name": "Nick Cave", "date": "2026-06-30", "venue": "Waldbühne"}
    e2 = {"name": "Nick Cave", "date": "2026-07-01", "venue": "Waldbühne"}
    assert _event_hash(1, e1) != _event_hash(1, e2)


def test_hash_handles_missing_fields():
    event = {"name": "Nick Cave"}
    assert isinstance(_event_hash(1, event), str)
    assert len(_event_hash(1, event)) == 64


# ── _QueueLogHandler stream isolation ────────────────────────────────────────


class _StubQueue:
    """Captures put_nowait calls — stands in for asyncio.Queue without a loop."""

    def __init__(self):
        self.items = []

    def put_nowait(self, item):
        self.items.append(item)


def _record(message: str) -> logging.LogRecord:
    return logging.LogRecord("pipeline", logging.INFO, __file__, 0, message, None, None)


def test_handler_drops_records_without_active_stream():
    queue = _StubQueue()
    handler = _QueueLogHandler(queue, stream_id=object())

    handler.emit(_record("hello"))

    assert not queue.items


def test_handler_captures_records_from_its_own_stream():
    queue = _StubQueue()
    stream_id = object()
    handler = _QueueLogHandler(queue, stream_id)

    token = _current_stream.set(stream_id)
    try:
        handler.emit(_record("mine"))
    finally:
        _current_stream.reset(token)

    assert len(queue.items) == 1


def test_handler_drops_records_from_a_foreign_stream():
    # The core of the cross-user leak fix: a handler must ignore records emitted
    # while a *different* stream is the active one.
    queue = _StubQueue()
    handler = _QueueLogHandler(queue, stream_id=object())

    token = _current_stream.set(object())  # someone else's stream
    try:
        handler.emit(_record("not mine"))
    finally:
        _current_stream.reset(token)

    assert not queue.items
