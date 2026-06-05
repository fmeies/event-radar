from app.constants import MAX_SEARCH_SITES
from app.prompts import parse_json, sites_hint


# ── parse_json ───────────────────────────────────────────────────────────────


def test_parse_json_plain_array():
    assert parse_json('[{"name": "A"}]', "ctx") == [{"name": "A"}]


def test_parse_json_fenced_array():
    assert parse_json('```json\n[{"name": "A"}]\n```', "ctx") == [{"name": "A"}]


def test_parse_json_strips_leading_prose():
    assert parse_json('Here you go: [{"name": "A"}]', "ctx") == [{"name": "A"}]


def test_parse_json_object_is_rejected():
    # A JSON object is not a list of events — it must never reach the callers,
    # which iterate the result and call .get() on each item.
    assert parse_json('{"name": "A"}', "ctx") == []


def test_parse_json_garbage_returns_empty():
    assert parse_json("not json at all", "ctx") == []


# ── sites_hint ───────────────────────────────────────────────────────────────


def test_sites_hint_empty_for_no_sites():
    assert sites_hint([]) == ""


def test_sites_hint_caps_at_max_sites():
    many = [f"site{i}.com" for i in range(MAX_SEARCH_SITES + 5)]
    assert sites_hint(many).count(".com") == MAX_SEARCH_SITES
