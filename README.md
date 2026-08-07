# Naukri Jobs API

Independent FastAPI service for searching and normalizing public Naukri job listings.

> This is not an official Naukri.com API and is not affiliated with Naukri.

## v1 architecture

- FastAPI + Pydantic
- Playwright collector
- Redis shared TTL cache in production, automatic in-memory fallback for development
- Per-query request coalescing inside each API process
- Pytest + GitHub Actions
- Docker / Docker Compose
- No PostgreSQL or Celery
- No Naukri login, credentials, saved cookies, or persistent browser profile

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --reload
```

Swagger: `http://127.0.0.1:8000/docs`

For the local headed diagnostic/verification mode that has been proven to work on macOS:

```bash
export NAUKRI_HEADLESS=false
uvicorn app.main:app --reload
```

## Search

```bash
curl "http://127.0.0.1:8000/v1/jobs/search?keyword=react&location=pune&experience=5&freshness=7&page=1&limit=20"
```

Parameters: `keyword` (required), `location`, `experience`, `freshness` (1-30 days), `work_mode` (`remote`, `hybrid`, `onsite`), `page` (>=1), and `limit` (1-50).

Responses include `X-Data-Source: live`, `cache`, or `stale-cache`.

## Cache

Set `REDIS_URL` to use Redis. Without it the service falls back to process-local memory. Defaults are 10 minutes for fresh cache and 1 hour for local stale fallback.

```bash
REDIS_URL=redis://localhost:6379/0
CACHE_TTL_SECONDS=600
CACHE_STALE_SECONDS=3600
```

`GET /health` reports `cache: redis` or `cache: memory`.

## Tests

Deterministic tests do not contact Naukri:

```bash
pytest -q
```

Live verification is deliberately separate because upstream behavior depends on the browser environment:

```bash
NAUKRI_HEADLESS=false python scripts/live_verify.py
```

The script checks multiple queries, pagination, limits, filters, normalized work mode, duplicate IDs, required job fields, and repeated-request caching.

## Docker Compose

```bash
docker compose up --build
```

This starts the API and Redis. Note: production deployment is not considered verified until the browser execution mode is proven in the target server environment; anonymous headless collection has previously received HTTP 403 while local headed Chromium succeeded.

## Production status

Application structure, validation, normalization, caching, CI, Docker configuration, and live verification tooling are implemented. Remaining release gates are environment-specific live browser verification, final data-quality verification against real results, production deployment verification, and RapidAPI marketplace wiring/load checks.
