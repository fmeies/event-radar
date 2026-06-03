from unittest.mock import patch

from app.claude_extractor import _parse_json, _sites_hint

EVENTS = [
    {
        "name": "Pixies",
        "date": "2026-06-30",
        "venue": "Zitadelle",
        "city": "Berlin",
        "url": None,
    }
]
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


# ── _sites_hint ────────────────────────────────────────────────────────────────


def test_sites_hint_empty():
    with patch("app.claude_extractor.settings") as mock:
        mock.search_sites = ""
        assert _sites_hint([]) == ""


def test_sites_hint_user_sites_only():
    with patch("app.claude_extractor.settings") as mock:
        mock.search_sites = ""
        assert (
            _sites_hint(["ra.co", "eventim.de"])
            == " Prefer results from: ra.co, eventim.de."
        )


def test_sites_hint_config_only():
    with patch("app.claude_extractor.settings") as mock:
        mock.search_sites = "ticketmaster.de"
        assert _sites_hint([]) == " Prefer results from: ticketmaster.de."


def test_sites_hint_merges_config_and_user():
    with patch("app.claude_extractor.settings") as mock:
        mock.search_sites = "ticketmaster.de"
        result = _sites_hint(["ra.co"])
        assert result == " Prefer results from: ticketmaster.de, ra.co."
