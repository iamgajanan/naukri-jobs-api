from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.schemas.jobs import SearchQuery, SearchResponse, WorkMode
from app.services.naukri import NaukriService, NaukriUpstreamError

router = APIRouter(prefix="/jobs", tags=["jobs"])
service = NaukriService()


@router.get("/search", response_model=SearchResponse)
async def search_jobs(
    keyword: Annotated[str, Query(min_length=1, max_length=100)],
    location: Annotated[str | None, Query(max_length=100)] = None,
    experience: Annotated[int | None, Query(ge=0, le=50)] = None,
    freshness: Annotated[int | None, Query(ge=1, le=30)] = None,
    work_mode: WorkMode | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
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
        raise HTTPException(status_code=503, detail={"code": "UPSTREAM_UNAVAILABLE", "message": str(exc)}) from exc

    if work_mode:
        jobs = [job for job in jobs if job.work_mode == work_mode]

    return SearchResponse(
        query=query,
        total_results=total,
        page=page,
        limit=limit,
        jobs=jobs,
    )
