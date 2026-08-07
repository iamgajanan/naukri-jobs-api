from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.schemas.jobs import SearchQuery, SearchResponse, WorkMode
from app.services.naukri import NaukriService, NaukriUpstreamError

router = APIRouter(prefix="/jobs", tags=["jobs"])
service = NaukriService()


@router.get("/search", response_model=SearchResponse)
async def search_jobs(
    keyword: str = Query(..., min_length=1, max_length=100),
    location: Optional[str] = Query(None, max_length=100),
    experience: Optional[int] = Query(None, ge=0, le=50),
    freshness: Optional[int] = Query(None, ge=1, le=30),
    work_mode: Optional[WorkMode] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
) -> SearchResponse:
    query = SearchQuery(
        keyword=keyword.strip(),
        location=location.strip() if location else None,
        experience=experience,
        freshness=freshness,
        work_mode=work_mode,
        page=page,
        limit=limit,
    )

    try:
        jobs, total = await service.search(query)
    except NaukriUpstreamError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "UPSTREAM_UNAVAILABLE", "message": str(exc)},
        ) from exc

    if work_mode:
        jobs = [job for job in jobs if job.work_mode == work_mode]

    return SearchResponse(
        query=query,
        total_results=total,
        page=page,
        limit=limit,
        jobs=jobs,
    )
