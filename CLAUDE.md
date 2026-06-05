# Event Radar — Project Notes for Claude

## Architecture

Two Docker containers sharing a SQLite volume:

- **`web`** — FastAPI app (uvicorn, port 8000, localhost-only)
- **`worker`** — supercronic runs `run_pipeline.py` daily at 08:00

```
app/
  config.py          # pydantic-settings, all env vars
  constants.py       # MAX_SEARCH_TERMS, MAX_SEARCH_SITES
  database.py        # SQLAlchemy engine + get_db dependency
  models.py          # User, SearchTerm, SearchSite, SeenEvent
  auth.py            # bcrypt passwords, JWT tokens, email verification tokens
  deps.py            # get_current_user FastAPI dependency
  templating.py      # single shared Jinja2Templates instance
  email_service.py   # aiosmtplib, send_verification_email + send_event_notification + send_admin_registration_notification
  claude_extractor.py # AsyncAnthropic — extract_events() (Brave mode) + search_and_extract_events() + discover_sites()
  search_pipeline.py  # orchestrates search → Claude → filter → dedup → email; site discovery
  logger.py          # centralised logging setup (DEBUG level, third-party libs suppressed)
  routers/
    auth.py          # /register /login /logout /verify
    dashboard.py     # /dashboard /terms /sites /location /pipeline/run /pipeline/stream /sites/discover/stream /sites/apply (SSE)
  templates/         # Jinja2 HTML (base, index, register, login, dashboard)
  static/style.css   # plain CSS, no framework
```

## Key decisions

- **Auth**: JWT in httpOnly cookie (`access_token`), 7-day expiry, `samesite=lax`
- **Email verification**: `itsdangerous.URLSafeTimedSerializer`, 24 h expiry
- **Admin notifications**: `send_admin_registration_notification()` is called after every successful registration. Target address is `ADMIN_EMAIL` (falls back to `FROM_EMAIL`). Failure is logged but does not affect the registration flow.
- **Deduplication**: SHA-256 hash of `user_id + name + date + venue` stored in `SeenEvent`. Insert uses `INSERT OR IGNORE` (`on_conflict_do_nothing()`) to survive any race conditions.
- **Event filtering**: Events are dropped if date is missing/unparseable, date is in the past, or city doesn't match the user's location. See `_is_valid_event()` in `search_pipeline.py`.
- **Event types**: Prompts cover concerts, readings, lectures, talks, signings, and all other public appearances — not concerts only.
- **Search mode** (`SEARCH_MODE` env var): comma-separated engine chain, tried in order until one returns results. Available engines:
  - `claude` — Claude web search + Claude extraction (Anthropic only)
  - `brave_claude` — Brave Search fetches snippets, Claude extracts structured data (needs `BRAVE_API_KEY` + `ANTHROPIC_API_KEY`)
  - `sonar` — Perplexity Sonar search + extraction (needs `PERPLEXITY_API_KEY`)
  - Examples: `claude,brave_claude` (default) | `sonar,claude,brave_claude` | `brave_claude`
- **Search sites**: per-user list of preferred domains (max 8). Passed as a soft hint in the prompt. Use the **Discover** button to let Claude suggest sites per watch list term; results are shown as checkboxes and only written to DB after the user clicks "Apply selected".
- **Pipeline concurrency**: per-user `asyncio.Lock` in `_user_locks` prevents duplicate runs. Lock lives in `run_for_user()` so both the SSE stream and background task share it. Discovery uses the same lock.
- **Live log streaming**: `GET /pipeline/stream` and `GET /sites/discover/stream` are SSE endpoints. They capture log output via `_QueueLogHandler` and stream it to the dashboard in real time. The discover stream yields a final `{"type":"result","sites":[...]}` message before closing so the JS can show a selection UI. Apache must be configured with `flushpackets=on` for SSE to work through the proxy.
- **Prefix stripping**: Apache does `ProxyPass /event-radar/ http://localhost:8000/ flushpackets=on` — trailing slash strips the prefix. FastAPI routes are all at root level (`/login`, `/dashboard`, etc.).
- **Redirects**: all `RedirectResponse` calls use `_redir()` helper which prepends `settings.root_path`. Apache `ProxyPassReverse` does not reliably rewrite relative `Location` headers, so the prefix must be in the URL.
- **Shared templates**: `app/templating.py` exports a single `templates` instance — do not create additional `Jinja2Templates` instances in routers.
- **`root_path`**: set via `ROOT_PATH` env var (e.g. `/event-radar`). Injected as a Jinja2 global in `templating.py` so all templates can prefix links and form actions. All template paths must use `{{ root_path }}/...` — never hardcode absolute paths. Do NOT set `root_path` on the FastAPI constructor — it breaks static file routing.
- **Password hashing**: `bcrypt` used directly (no passlib — passlib is incompatible with bcrypt 4.x).
- **Timezones**: Docker containers run with `TZ=Europe/Berlin` so log timestamps and the 08:00 cron match the host timezone.

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
