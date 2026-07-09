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


def test_parse_json_strips_trailing_prose():
    # Claude web search appends explanatory notes after the array; a plain
    # json.loads fails here with "Extra data" and would drop real events.
    raw = '[{"name": "A"}]\n\nNote: these are the only confirmed events.'
    assert parse_json(raw, "ctx") == [{"name": "A"}]


def test_parse_json_empty_array_with_prose_is_not_a_warning():
    # The exact shape seen in production: contradictory prose around an empty
    # array. The correct result is "no events", not a parse failure.
    raw = "I found one event:\n\n[]\n\nNote: actually none are confirmed."
    assert parse_json(raw, "ctx") == []


def test_parse_json_skips_citation_markers():
    # A bracketed citation like [1] must not be mistaken for the events array.
    raw = 'See the keynote [1]. Events: [{"name": "A"}]'
    assert parse_json(raw, "ctx") == [{"name": "A"}]


def test_parse_json_citation_only_returns_empty():
    raw = "A past keynote [1] but no upcoming events were found."
    assert parse_json(raw, "ctx") == []


def test_parse_json_filters_non_dict_items():
    assert parse_json('[{"name": "A"}, 5, "x"]', "ctx") == [{"name": "A"}]


def test_parse_json_truncated_array_returns_empty():
    # An unterminated array (e.g. hit max_tokens) is genuinely malformed.
    assert parse_json('[{"name": "A"}', "ctx") == []


# ── sites_hint ───────────────────────────────────────────────────────────────


def test_sites_hint_empty_for_no_sites():
    assert sites_hint([]) == ""


def test_sites_hint_caps_at_max_sites():
    many = [f"site{i}.com" for i in range(MAX_SEARCH_SITES + 5)]
    assert sites_hint(many).count(".com") == MAX_SEARCH_SITES
