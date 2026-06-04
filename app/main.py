from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded

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


async def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    log.warning(
        "Rate limit exceeded: %s %s from %s (%s)",
        request.method,
        request.url.path,
        request.client,
        exc.detail,
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
    log.info("Database ready")
    yield


app = FastAPI(title="Event Radar", lifespan=lifespan)
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
