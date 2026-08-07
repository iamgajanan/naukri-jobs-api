from typing import Dict, List, Set, Tuple, Union
from urllib.parse import quote_plus

import httpx

from app.schemas.jobs import Job, SearchQuery
from app.utils.normalizers import normalize_experience, normalize_salary, normalize_work_mode


class NaukriUpstreamError(Exception):
    def __init__(self, message: str, status_code=None, response_preview=None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_preview = response_preview


class NaukriService:
    SEARCH_URL = "https://www.naukri.com/jobapi/v3/search"

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout

    def _headers(self, query: SearchQuery) -> Dict[str, str]:
        keyword = quote_plus(query.keyword)
        location = quote_plus(query.location or "")
        referer = "https://www.naukri.com/{}-jobs-in-{}".format(keyword, location)
        return {
            "accept": "application/json",
            "accept-language": "en-US,en;q=0.9",
            "appid": "109",
            "clientid": "d3skt0p",
            "content-type": "application/json",
            "referer": referer,
            "systemid": "109",
            "user-agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        }

    def _params(self, query: SearchQuery) -> Dict[str, Union[str, int]]:
        params = {
            "noOfResults": query.limit,
            "urlType": "search_by_key_loc" if query.location else "search_by_keyword",
            "searchType": "adv",
            "keyword": query.keyword,
            "pageNo": query.page,
            "src": "directSearch",
        }
        if query.location:
            params["location"] = query.location
        if query.experience is not None:
            params["experience"] = query.experience
        if query.freshness is not None:
            params["jobAge"] = query.freshness
        return params

    async def search(self, query: SearchQuery) -> Tuple[List[Job], int]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(
                    self.SEARCH_URL,
                    params=self._params(query),
                    headers=self._headers(query),
                )
        except httpx.HTTPError as exc:
            raise NaukriUpstreamError("Could not connect to Naukri: {}".format(type(exc).__name__)) from exc

        if response.status_code >= 400:
            preview = response.text[:300].replace("\n", " ")
            raise NaukriUpstreamError(
                "Naukri returned HTTP {}".format(response.status_code),
                status_code=response.status_code,
                response_preview=preview,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            preview = response.text[:300].replace("\n", " ")
            raise NaukriUpstreamError(
                "Naukri returned a non-JSON response",
                status_code=response.status_code,
                response_preview=preview,
            ) from exc

        raw_jobs = payload.get("jobDetails") or payload.get("jobs") or []
        jobs = []  # type: List[Job]
        seen = set()  # type: Set[str]

        for raw in raw_jobs:
            job_id = str(raw.get("jobId") or raw.get("id") or "").strip()
            url = raw.get("jdURL") or raw.get("jobUrl") or raw.get("url")
            if url and str(url).startswith("/"):
                url = "https://www.naukri.com{}".format(url)
            if not job_id:
                job_id = str(url or "").strip()
            if not job_id or not url or job_id in seen:
                continue
            seen.add(job_id)

            skills = raw.get("tagsAndSkills") or raw.get("skills") or []
            if isinstance(skills, str):
                skills = [item.strip() for item in skills.split(",") if item.strip()]

            placeholders = raw.get("placeholders") or []
            location = raw.get("location")
            if placeholders and isinstance(placeholders[0], dict):
                location = placeholders[0].get("label") or location

            jobs.append(
                Job(
                    id=job_id,
                    title=raw.get("title") or raw.get("jobTitle") or "Unknown",
                    company=raw.get("companyName") or raw.get("company"),
                    location=location,
                    experience=normalize_experience(raw.get("experienceText") or raw.get("experience")),
                    salary=normalize_salary(raw.get("salaryText") or raw.get("salary")),
                    work_mode=normalize_work_mode(raw.get("workMode") or raw.get("wfhType")),
                    employment_type=raw.get("employmentType"),
                    skills=skills if isinstance(skills, list) else [],
                    description=raw.get("jobDescription") or raw.get("description"),
                    posted_at=raw.get("createdDate") or raw.get("footerPlaceholderLabel") or raw.get("postedDate"),
                    job_url=str(url),
                )
            )

        total = payload.get("noOfJobs") or payload.get("totalJobs") or payload.get("totalResults") or len(jobs)
        try:
            total = int(total)
        except (TypeError, ValueError):
            total = len(jobs)
        return jobs, total
