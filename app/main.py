from fastapi import FastAPI

from app.api.v1.jobs import router as jobs_router

app = FastAPI(
    title="Naukri Jobs API",
    description="A clean API for searching and normalizing public job listings.",
    version="1.0.0",
)


@app.get("/", tags=["system"])
async def root() -> dict[str, str]:
    return {"name": "Naukri Jobs API", "version": "1.0.0"}


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(jobs_router, prefix="/v1")
