# Naukri Jobs API

A lightweight FastAPI service for searching and normalizing public Naukri job listings.

> This project is an independent API project and is not an official Naukri.com API.

## v1 stack

- FastAPI
- HTTPX
- Pydantic
- Docker
- Pytest

No PostgreSQL, Redis, Celery, browser profile, or Naukri login is required by the current architecture.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open Swagger at `http://127.0.0.1:8000/docs`.

## Health

```bash
curl http://127.0.0.1:8000/health
```

## Search

```bash
curl "http://127.0.0.1:8000/v1/jobs/search?keyword=react&location=pune&experience=5&freshness=7&limit=20"
```

Supported query parameters:

- `keyword` - required
- `location`
- `experience` - years
- `freshness` - maximum job age in days
- `work_mode` - `remote`, `hybrid`, or `onsite`
- `page` - defaults to 1
- `limit` - 1 to 50, defaults to 20

## Tests

```bash
pytest
```

## Docker

```bash
docker build -t naukri-jobs-api .
docker run --rm -p 8000:8000 naukri-jobs-api
```

## API response

The public response is normalized so API consumers do not have to understand upstream field names. Salary values are normalized to INR amounts when possible, experience is represented as min/max years, duplicate IDs are removed, and upstream failures return HTTP 503 rather than exposing internal exceptions.

## Next milestone

Validate the upstream search integration against multiple real queries and harden field mapping, retry behavior, rate limiting, caching, and deployment before commercial release.
