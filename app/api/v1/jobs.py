import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response

from app.schemas.jobs import SearchQuery, SearchResponse, WorkMode
from app.services.collector import collection_service
from app.services.naukri import NaukriUpstreamError

router = APIRouter(prefix="/jobs", tags=["jobs"])
logger = logging.getLogger(__name__)


@router.get("/search", response_model=SearchResponse)
async def search_jobs(
    response: Response,
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
        jobs, total, source = await collection_service.search(query)
    except NaukriUpstreamError as exc:
        logger.warning(
            "Naukri upstream unavailable: %s status=%s preview=%s",
            exc,
            exc.status_code,
            exc.response_preview,
        )
        detail = {"code": "UPSTREAM_UNAVAILABLE", "message": str(exc)}
        if exc.status_code is not None:
            detail["upstream_status"] = exc.status_code
        if exc.response_preview:
            detail["upstream_preview"] = exc.response_preview
        raise HTTPException(status_code=503, detail=detail) from exc
    except Exception as exc:
        # Keep exception details out of the public response, but log the full
        # traceback server-side so Docker/Railway failures are diagnosable.
        logger.exception("Collector failed for query=%s: %s", query, exc)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "COLLECTOR_UNAVAILABLE",
                "message": "Job collection is temporarily unavailable",
            },
        ) from exc

    response.headers["X-Data-Source"] = source

    return SearchResponse(
        query=query,
        total_results=total,
        page=page,
        limit=limit,
        jobs=jobs,
    )
