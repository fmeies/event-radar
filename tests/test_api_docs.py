import pytest
from fastapi.testclient import TestClient

from app.main import app

# No context manager: the lifespan (database setup) is not needed for these routes
client = TestClient(app)

HTTP_NOT_FOUND = 404
HTTP_OK = 200


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_generated_api_docs_are_not_served(path):
    assert client.get(path).status_code == HTTP_NOT_FOUND


def test_health_still_served():
    assert client.get("/health").status_code == HTTP_OK
