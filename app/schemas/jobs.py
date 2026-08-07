from typing import List, Literal, Optional

from pydantic import BaseModel, Field


WorkMode = Literal["remote", "hybrid", "onsite"]


class Experience(BaseModel):
    text: Optional[str] = None
    min: Optional[int] = None
    max: Optional[int] = None


class Salary(BaseModel):
    text: Optional[str] = None
    min: Optional[int] = None
    max: Optional[int] = None
    currency: Optional[str] = "INR"


class Job(BaseModel):
    id: str
    title: str
    company: Optional[str] = None
    location: Optional[str] = None
    experience: Experience = Field(default_factory=Experience)
    salary: Salary = Field(default_factory=Salary)
    work_mode: Optional[str] = None
    employment_type: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    posted_at: Optional[str] = None
    job_url: str
    source: str = "naukri"


class SearchQuery(BaseModel):
    keyword: str
    location: Optional[str] = None
    experience: Optional[int] = None
    freshness: Optional[int] = None
    work_mode: Optional[WorkMode] = None
    page: int = 1
    limit: int = 20


class SearchResponse(BaseModel):
    status: Literal["success"] = "success"
    query: SearchQuery
    total_results: int
    page: int
    limit: int
    jobs: List[Job]
