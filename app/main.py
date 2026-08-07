from fastapi import FastAPI

from app.api.v1.jobs import router as jobs_router
from app.services.cache import search_cache

app = FastAPI(
    title="Naukri Jobs API",
    description="Independent API for searching and normalizing public job listings.",
    version="1.0.0",
)


@app.get("/", tags=["system"])
async def root():
    return {"name": "Naukri Jobs API", "version": "1.0.0"}


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "cache": search_cache.backend}


app.include_router(jobs_router, prefix="/v1")
