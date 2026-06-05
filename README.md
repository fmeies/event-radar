# Event Radar

Automated event monitoring tool. Users are notified by email when artists, authors, bands, or speakers from their personal watch list perform in their city.

## How it works

1. Users register and configure a location (e.g. "Berlin") and a watch list of names
2. Every day at 08:00 the search pipeline runs for all verified users
3. For each name on the watch list, [Claude](https://anthropic.com) searches the web and extracts structured event data (name, date, venue, URL)
4. Events include concerts, readings, lectures, talks, and other public appearances
5. Events without a clean future date or matching city are discarded
6. New events (not previously reported) trigger an email notification

A **Search now** button in the dashboard triggers the pipeline manually and streams the log live in the browser.

A **Discover** button lets Claude suggest the best websites for each watch list entry. The user can then select which sites to add as preferred search sources.

An **Active / Paused** toggle lets each user pause the daily search without deleting their watch list. Paused users are skipped by the 08:00 pipeline.

## Requirements

- Docker + Docker Compose
- [Anthropic API key](https://console.anthropic.com/)
- [Brave Search API key](https://api.search.brave.com/) (optional — free tier: 2 000 queries/month, used as fallback)
- An SMTP server (Gmail works — see below)

## Setup

```bash
git clone ...
cd event-radar
cp .env.example .env
# Fill in .env (see Configuration below)
docker compose up --build
```

The app is now available at `http://localhost:8000`.

## Configuration

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | ✅ | Random secret for JWT and email tokens. Generate with: `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `ANTHROPIC_API_KEY` | ✅ | Anthropic API key |
| `BRAVE_API_KEY` | | Brave Search API key — required for the `brave_claude` engine |
| `PERPLEXITY_API_KEY` | | Perplexity API key — required for the `sonar` engine |
| `DATABASE_URL` | | Default: `sqlite:////data/event_radar.db` |
| `SMTP_HOST` | ✅ | SMTP server hostname |
| `SMTP_PORT` | | Default: `587` (STARTTLS). Use `465` for SSL |
| `SMTP_USER` | | SMTP username (leave empty for unauthenticated) |
| `SMTP_PASSWORD` | | SMTP password |
| `FROM_EMAIL` | ✅ | Sender address |
| `ADMIN_EMAIL` | | Receives a notification when a new user registers. Defaults to `FROM_EMAIL`. |
| `BASE_URL` | ✅ | Public URL of this instance including path prefix — used in verification email links (e.g. `https://yourdomain.com/event-radar`) |
| `ROOT_PATH` | | URL prefix when served under a sub-path (e.g. `/event-radar`). Leave empty for root. |
| `SECURE_COOKIES` | | Set to `true` when serving over HTTPS |
| `SEARCH_MODE` | | Comma-separated engine chain. Default: `claude,brave_claude`. See Search modes below. |

### Search modes

`SEARCH_MODE` is a comma-separated list of engines, tried in order until one returns results. This makes later engines act as fallbacks for earlier ones.

| Engine | Behaviour | Requires |
|---|---|---|
| `claude` | Claude uses its built-in web search to find and extract events in one step. | `ANTHROPIC_API_KEY` |
| `brave_claude` | Brave Search fetches result snippets, Claude extracts structured event data from them. | `BRAVE_API_KEY` + `ANTHROPIC_API_KEY` |
| `sonar` | Perplexity Sonar searches and extracts events. | `PERPLEXITY_API_KEY` |

Examples: `claude,brave_claude` (default) · `brave_claude` · `sonar,claude,brave_claude`

### Gmail SMTP

1. Enable 2-factor authentication on your Google account
2. Create an [App Password](https://myaccount.google.com/apppasswords)
3. Set `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, and use the 16-character app password (without spaces) as `SMTP_PASSWORD`

## Apache reverse proxy

```apache
ProxyPass        /event-radar/ http://localhost:8000/ flushpackets=on
ProxyPassReverse /event-radar/ http://localhost:8000/
```

`flushpackets=on` is required for the live log stream (SSE) to work. The trailing slashes are required — Apache strips the `/event-radar` prefix before forwarding to the app.

## Viewing registered users

```bash
docker compose exec web python -c "
from app.database import SessionLocal
from app.models import User
db = SessionLocal()
for u in db.query(User).all():
    print(u.id, u.email, u.is_verified, u.location)
"
```

## Listing registered users

```bash
docker compose exec web python list_users.py
```

Shows all users with their verification status, location, watch list, and search sites.

## Running the search pipeline manually

Either click **Search now** in the dashboard (shows a live log), or run the pipeline for all users from the host:

```bash
docker compose exec worker python run_pipeline.py
```
