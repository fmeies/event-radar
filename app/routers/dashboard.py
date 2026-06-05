import json
import re

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    StreamingResponse,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..constants import MAX_SEARCH_SITES, MAX_SEARCH_TERMS
from ..database import get_db
from ..deps import get_current_user
from ..limiter import limiter
from ..models import SearchSite, SearchTerm, User
from ..search_pipeline import run_discovery_for_user_streamed, run_for_user_streamed
from ..templating import templates
from ..utils import redir as _redir

_DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?(\.[a-z0-9\-]+)+$")


class _ApplySitesRequest(BaseModel):
    sites: list[str]


router = APIRouter()

_ERRORS = {
    "too_many_terms": f"You can track at most {MAX_SEARCH_TERMS} search terms.",
    "too_many_sites": f"You can add at most {MAX_SEARCH_SITES} search sites.",
}


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    msg: str = "",
    error: str = "",
    user: User = Depends(get_current_user),
):
    if not user:
        return _redir("/login")

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "terms": user.search_terms,
            "sites": user.search_sites,
            "max_terms": MAX_SEARCH_TERMS,
            "max_sites": MAX_SEARCH_SITES,
            "success": "Location saved." if msg == "location_saved" else "",
            "error": _ERRORS.get(error, ""),
        },
    )


@router.post("/terms/add")
async def add_term(
    term: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user:
        return _redir("/login")

    term = term.strip()
    if not term:
        return _redir("/dashboard")

    count = db.query(SearchTerm).filter(SearchTerm.user_id == user.id).count()
    if count >= MAX_SEARCH_TERMS:
        return _redir("/dashboard?error=too_many_terms")

    duplicate = (
        db.query(SearchTerm)
        .filter(SearchTerm.user_id == user.id, SearchTerm.term == term)
        .first()
    )
    if not duplicate:
        db.add(SearchTerm(user_id=user.id, term=term))
        db.commit()

    return _redir("/dashboard")


@router.post("/terms/{term_id}/delete")
async def delete_term(
    term_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user:
        return _redir("/login")

    term = (
        db.query(SearchTerm)
        .filter(SearchTerm.id == term_id, SearchTerm.user_id == user.id)
        .first()
    )
    if term:
        db.delete(term)
        db.commit()

    return _redir("/dashboard")


@router.post("/sites/add")
async def add_site(
    site: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user:
        return _redir("/login")

    site = (
        site.strip()
        .lower()
        .removeprefix("https://")
        .removeprefix("http://")
        .rstrip("/")
    )
    if not site:
        return _redir("/dashboard")

    count = db.query(SearchSite).filter(SearchSite.user_id == user.id).count()
    if count >= MAX_SEARCH_SITES:
        return _redir("/dashboard?error=too_many_sites")

    duplicate = (
        db.query(SearchSite)
        .filter(SearchSite.user_id == user.id, SearchSite.site == site)
        .first()
    )
    if not duplicate:
        db.add(SearchSite(user_id=user.id, site=site))
        db.commit()

    return _redir("/dashboard")


@router.post("/sites/{site_id}/delete")
async def delete_site(
    site_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user:
        return _redir("/login")

    site = (
        db.query(SearchSite)
        .filter(SearchSite.id == site_id, SearchSite.user_id == user.id)
        .first()
    )
    if site:
        db.delete(site)
        db.commit()

    return _redir("/dashboard")


@router.post("/location")
async def update_location(
    location: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user:
        return _redir("/login")

    location = location.strip()[:100]
    user.location = location
    db.commit()

    return _redir("/dashboard?msg=location_saved")


@router.get("/pipeline/stream")
@limiter.limit("6/hour")
async def stream_pipeline(request: Request, user: User = Depends(get_current_user)):
    if not user:
        return _redir("/login")

    async def event_stream():
        async for line in run_for_user_streamed(user.id):
            yield f"data: {json.dumps(line)}\n\n"
        yield "data: null\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/sites/discover/stream")
@limiter.limit("6/hour")
async def discover_sites_stream(
    request: Request, user: User = Depends(get_current_user)
):
    if not user:
        return _redir("/login")

    async def event_stream():
        async for line in run_discovery_for_user_streamed(user.id):
            yield f"data: {json.dumps(line)}\n\n"
        yield "data: null\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/sites/apply")
async def apply_discovered_sites(
    payload: _ApplySitesRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    normalised = []
    for raw in payload.sites:
        site = (
            raw.strip()
            .lower()
            .removeprefix("https://")
            .removeprefix("http://")
            .rstrip("/")
        )
        if site and len(site) <= 100 and _DOMAIN_RE.match(site):
            normalised.append(site)

    for old in user.search_sites:
        db.delete(old)

    for site in normalised[:MAX_SEARCH_SITES]:
        db.add(SearchSite(user_id=user.id, site=site))

    db.commit()
    return JSONResponse({"ok": True, "count": len(normalised[:MAX_SEARCH_SITES])})


@router.post("/search/toggle")
async def toggle_search(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user:
        return _redir("/login")

    user.search_enabled = not user.search_enabled
    db.commit()

    return _redir("/dashboard")


@router.post("/account/delete")
async def delete_account(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user:
        return _redir("/login")

    db.delete(user)
    db.commit()

    response = _redir("/")
    response.delete_cookie("access_token")
    return response
