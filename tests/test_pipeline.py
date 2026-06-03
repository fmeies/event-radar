from datetime import date, timedelta

from app.search_pipeline import _event_hash, _is_valid_event

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
