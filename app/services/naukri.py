from urllib.parse import quote_plus

import httpx

from app.schemas.jobs import Job, SearchQuery
from app.utils.normalizers import normalize_experience, normalize_salary, normalize_work_mode


class NaukriUpstreamError(Exception):
    pass


class NaukriService:
    SEARCH_URL = "https://www.naukri.com/jobapi/v3/search"

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout

    def _headers(self, query: SearchQuery) -> dict[str, str]:
        keyword = quote_plus(query.keyword)
        location = quote_plus(query.location or "")
        referer = f"https://www.naukri.com/{keyword}-jobs-in-{location}"
        return {
            "accept": "application/json",
            "accept-language": "en-US,en;q=0.9",
            "appid": "109",
            "clientid": "d3skt0p",
            "referer": referer,
            "systemid": "Naukri",
            "user-agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        }

    def _params(self, query: SearchQuery) -> dict[str, str | int]:
        params: dict[str, str | int] = {
            "noOfResults": query.limit,
            "urlType": "search_by_keyword",
            "searchType": "adv",
            "keyword": query.keyword,
            "pageNo": query.page,
        }
        if query.location:
            params["location"] = query.location
        if query.experience is not None:
            params["experience"] = query.experience
        if query.freshness is not None:
            params["jobAge"] = query.freshness
        return params

    async def search(self, query: SearchQuery) -> tuple[list[Job], int]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(
                    self.SEARCH_URL,
                    params=self._params(query),
                    headers=self._headers(query),
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise NaukriUpstreamError("Naukri search is temporarily unavailable") from exc

        raw_jobs = payload.get("jobDetails") or payload.get("jobs") or []
        jobs: list[Job] = []
        seen: set[str] = set()

        for raw in raw_jobs:
            job_id = str(raw.get("jobId") or raw.get("id") or "").strip()
            url = raw.get("jdURL") or raw.get("jobUrl") or raw.get("url")
            if url and str(url).startswith("/"):
                url = f"https://www.naukri.com{url}"
            if not job_id:
                job_id = str(url or "").strip()
            if not job_id or not url or job_id in seen:
                continue
            seen.add(job_id)

            skills = raw.get("tagsAndSkills") or raw.get("skills") or []
            if isinstance(skills, str):
                skills = [item.strip() for item in skills.split(",") if item.strip()]

            job = Job(
                id=job_id,
                title=raw.get("title") or raw.get("jobTitle") or "Unknown",
                company=raw.get("companyName") or raw.get("company"),
                location=raw.get("placeholders", [{}])[0].get("label") if raw.get("placeholders") else raw.get("location"),
                experience=normalize_experience(raw.get("experienceText") or raw.get("experience")),
                salary=normalize_salary(raw.get("salaryText") or raw.get("salary")),
                work_mode=normalize_work_mode(raw.get("workMode") or raw.get("wfhType")),
                employment_type=raw.get("employmentType"),
                skills=skills if isinstance(skills, list) else [],
                description=raw.get("jobDescription") or raw.get("description"),
                posted_at=raw.get("createdDate") or raw.get("footerPlaceholderLabel") or raw.get("postedDate"),
                job_url=str(url),
            )
            jobs.append(job)

        total = payload.get("noOfJobs") or payload.get("totalJobs") or payload.get("totalResults") or len(jobs)
        try:
            total = int(total)
        except (TypeError, ValueError):
            total = len(jobs)
        return jobs, total
