from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from sqlalchemy import text

from .config import settings
from .database import engine
from .deps import get_current_user
from .limiter import limiter
from .logger import get_logger, setup_logging
from .models import Base
from .routers import auth, dashboard
from .templating import templates

setup_logging()

log = get_logger("web")
BASE_DIR = Path(__file__).parent


async def _rate_limit_exceeded_handler(request: Request, exc: Exception):
    rate_exc = cast(RateLimitExceeded, exc)
    log.warning(
        "Rate limit exceeded: %s %s from %s (%s)",
        request.method,
        request.url.path,
        request.client,
        rate_exc.detail,
    )
    if "text/html" in request.headers.get("accept", ""):
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "user": None,
                "error": "Too many requests — please wait a moment.",
            },
            status_code=429,
        )
    return JSONResponse({"detail": "Too many requests"}, status_code=429)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        cols = [row[1] for row in conn.execute(text("PRAGMA table_info(users)"))]
        if "search_enabled" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN search_enabled BOOLEAN NOT NULL DEFAULT 1"
                )
            )
            conn.commit()
            log.info("Migration: added search_enabled column")
    log.info("Database ready")
    yield


_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _origin_from_url(url: str) -> str:
    """Extract scheme+host from a URL, stripping path and trailing slash."""
    if "//" in url:
        return url.split("/")[0] + "//" + url.split("//")[-1].split("/")[0]
    return url


_ALLOWED_HOSTS = {_origin_from_url(settings.base_url)}


class _CSRFMiddleware(BaseHTTPMiddleware):
    """Reject cross-origin state-mutating requests by checking Origin/Referer."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method not in _SAFE_METHODS:
            origin = request.headers.get("origin") or request.headers.get("referer", "")
            # Strip path from referer so https://host/path matches https://host
            origin_root = (
                origin.split("/")[0] + "//" + origin.split("//")[-1].split("/")[0]
                if "//" in origin
                else origin
            )
            if origin and origin_root not in _ALLOWED_HOSTS:
                log.warning("CSRF check failed: origin=%s", origin)
                return JSONResponse({"detail": "Forbidden"}, status_code=403)
        return await call_next(request)


app = FastAPI(title="Event Radar", lifespan=lifespan)
app.add_middleware(_CSRFMiddleware)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

app.include_router(auth.router)
app.include_router(dashboard.router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, user=Depends(get_current_user)):
    return templates.TemplateResponse("index.html", {"request": request, "user": user})


@app.get("/health")
async def health():
    return {"status": "ok"}
