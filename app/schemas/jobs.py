from typing import Literal

from pydantic import BaseModel, Field


WorkMode = Literal["remote", "hybrid", "onsite"]


class Experience(BaseModel):
    text: str | None = None
    min: int | None = None
    max: int | None = None


class Salary(BaseModel):
    text: str | None = None
    min: int | None = None
    max: int | None = None
    currency: str | None = "INR"


class Job(BaseModel):
    id: str
    title: str
    company: str | None = None
    location: str | None = None
    experience: Experience = Field(default_factory=Experience)
    salary: Salary = Field(default_factory=Salary)
    work_mode: str | None = None
    employment_type: str | None = None
    skills: list[str] = Field(default_factory=list)
    description: str | None = None
    posted_at: str | None = None
    job_url: str
    source: str = "naukri"


class SearchQuery(BaseModel):
    keyword: str
    location: str | None = None
    experience: int | None = None
    freshness: int | None = None
    work_mode: WorkMode | None = None
    page: int = 1
    limit: int = 20


class SearchResponse(BaseModel):
    status: Literal["success"] = "success"
    query: SearchQuery
    total_results: int
    page: int
    limit: int
    jobs: list[Job]
