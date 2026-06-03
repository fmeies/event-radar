# Event Radar — Project Notes for Claude

## Architecture

Two Docker containers sharing a SQLite volume:

- **`web`** — FastAPI app (uvicorn, port 8000, localhost-only)
- **`worker`** — supercronic runs `run_pipeline.py` daily at 08:00

```
app/
  config.py          # pydantic-settings, all env vars
  database.py        # SQLAlchemy engine + get_db dependency
  models.py          # User, SearchTerm, SeenEvent
  auth.py            # bcrypt passwords, JWT tokens, email verification tokens
  deps.py            # get_current_user FastAPI dependency
  templating.py      # single shared Jinja2Templates instance
  email_service.py   # aiosmtplib, send_verification_email + send_event_notification
  claude_extractor.py # AsyncAnthropic — extract_events() (Brave mode) + search_and_extract_events() (Claude web search mode)
  search_pipeline.py  # orchestrates search → Claude → filter → dedup → email
  logger.py          # centralised logging setup (DEBUG level, third-party libs suppressed)
  routers/
    auth.py          # /register /login /logout /verify
    dashboard.py     # /dashboard /terms /location /pipeline/run /pipeline/stream (SSE)
  templates/         # Jinja2 HTML (base, index, register, login, dashboard)
  static/style.css   # plain CSS, no framework
```

## Key decisions

- **Auth**: JWT in httpOnly cookie (`access_token`), 7-day expiry, `samesite=lax`
- **Email verification**: `itsdangerous.URLSafeTimedSerializer`, 24 h expiry
- **Deduplication**: SHA-256 hash of `user_id + name + date + venue` stored in `SeenEvent`. Insert uses `INSERT OR IGNORE` (`on_conflict_do_nothing()`) to survive any race conditions.
- **Event filtering**: Events are dropped if date is missing/unparseable, date is in the past, or city doesn't match the user's location. See `_is_valid_event()` in `search_pipeline.py`.
- **Search mode** (`SEARCH_MODE` env var):
  - `claude` (default) — Claude uses the `web_search_20250305` built-in tool to search and extract in one step. Falls back to Brave if Claude returns 0 results and `BRAVE_API_KEY` is set.
  - `brave` — Brave Search fetches snippets, Claude extracts structured data from them.
- **Pipeline concurrency**: per-user `asyncio.Lock` in `_user_locks` prevents duplicate runs. Lock lives in `run_for_user()` so both the SSE stream and background task share it.
- **Live log streaming**: `GET /pipeline/stream` is an SSE endpoint. It captures log output via `_QueueLogHandler` and streams it to the dashboard in real time. Apache must be configured with `flushpackets=on` for SSE to work through the proxy.
- **Prefix stripping**: Apache does `ProxyPass /event-radar/ http://localhost:8000/ flushpackets=on` — trailing slash strips the prefix. FastAPI routes are all at root level (`/login`, `/dashboard`, etc.).
- **Redirects**: all `RedirectResponse` calls use `_redir()` helper which prepends `settings.root_path`. Apache `ProxyPassReverse` does not reliably rewrite relative `Location` headers, so the prefix must be in the URL.
- **Shared templates**: `app/templating.py` exports a single `templates` instance — do not create additional `Jinja2Templates` instances in routers.
- **`root_path`**: set via `ROOT_PATH` env var (e.g. `/event-radar`). Injected as a Jinja2 global in `templating.py` so all templates can prefix links and form actions. All template paths must use `{{ root_path }}/...` — never hardcode absolute paths. Do NOT set `root_path` on the FastAPI constructor — it breaks static file routing.
- **Password hashing**: `bcrypt` used directly (no passlib — passlib is incompatible with bcrypt 4.x).

## Running locally (without Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in required fields
uvicorn app.main:app --reload
```

The SQLite DB is created automatically on first start at the path set in `DATABASE_URL`.

## Running the pipeline locally

```bash
python run_pipeline.py
```

## Conventions

- All user-visible text is in English
- Error messages from the pipeline use `log.error(..., exc_info=True)` for full tracebacks
- Redirects always use status code 303 via `_redir()` helper in each router
- Template context always includes `user` (may be `None` for public pages)
- `SECURE_COOKIES=true` must be set in production (HTTPS)
