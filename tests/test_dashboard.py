import asyncio

from app.routers.dashboard import toggle_search


class _FakeUser:
    def __init__(self, search_enabled):
        self.search_enabled = search_enabled


class _FakeDB:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


def _run(coro):
    return asyncio.run(coro)


# ── /search/toggle ───────────────────────────────────────────────────────────


def test_toggle_turns_paused_user_active():
    user = _FakeUser(search_enabled=False)
    db = _FakeDB()

    response = _run(toggle_search(db=db, user=user))

    assert user.search_enabled is True
    assert db.commits == 1
    assert response.status_code == 303
    assert response.headers["location"].endswith("/dashboard")


def test_toggle_turns_active_user_paused():
    user = _FakeUser(search_enabled=True)
    db = _FakeDB()

    response = _run(toggle_search(db=db, user=user))

    assert user.search_enabled is False
    assert db.commits == 1
    assert response.status_code == 303
    assert response.headers["location"].endswith("/dashboard")


def test_toggle_without_user_redirects_to_login():
    db = _FakeDB()

    response = _run(toggle_search(db=db, user=None))

    assert db.commits == 0
    assert response.status_code == 303
    assert response.headers["location"].endswith("/login")
