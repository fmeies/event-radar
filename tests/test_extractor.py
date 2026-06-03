from app.claude_extractor import _parse_json

EVENTS = [{"name": "Pixies", "date": "2026-06-30", "venue": "Zitadelle", "city": "Berlin", "url": None}]
EVENTS_JSON = '[{"name": "Pixies", "date": "2026-06-30", "venue": "Zitadelle", "city": "Berlin", "url": null}]'


def test_plain_json():
    assert _parse_json(EVENTS_JSON, "test") == EVENTS


def test_strips_json_code_fence():
    raw = f"```json\n{EVENTS_JSON}\n```"
    assert _parse_json(raw, "test") == EVENTS


def test_strips_plain_code_fence():
    raw = f"```\n{EVENTS_JSON}\n```"
    assert _parse_json(raw, "test") == EVENTS


def test_empty_array():
    assert _parse_json("[]", "test") == []


def test_invalid_json_returns_empty():
    assert _parse_json("not json", "test") == []


def test_truncated_json_returns_empty():
    assert _parse_json('[{"name": "Pixies"', "test") == []


def test_empty_string_returns_empty():
    assert _parse_json("", "test") == []
