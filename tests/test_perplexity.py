import asyncio

from app import perplexity_extractor
from app.config import settings


class _FakeResponse:
    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {"choices": [{"message": {"content": "[]"}}]}


def _search_and_capture_payload(monkeypatch) -> dict:
    """Run search_events with a stubbed HTTP client and return the JSON body sent."""
    captured: dict = {}

    class _FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self) -> "_FakeClient":
            return self

        async def __aexit__(self, *args) -> bool:
            return False

        async def post(self, url, headers=None, json=None):
            captured["json"] = json
            return _FakeResponse()

    monkeypatch.setattr(perplexity_extractor.httpx, "AsyncClient", _FakeClient)
    asyncio.run(perplexity_extractor.search_events("X", "Berlin", 2026))
    return captured["json"]


def test_request_uses_configured_model(monkeypatch):
    # Guards against re-hardcoding the model: whatever PERPLEXITY_MODEL is set to
    # must be the model sent to Perplexity.
    monkeypatch.setattr(settings, "perplexity_model", "sonar-pro")
    payload = _search_and_capture_payload(monkeypatch)
    assert payload["model"] == "sonar-pro"
