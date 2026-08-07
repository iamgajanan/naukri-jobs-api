from app.schemas.jobs import Experience
from app.utils.normalizers import (
    experience_matches,
    freshness_matches,
    normalize_employment_type,
    normalize_experience,
    normalize_salary,
    normalize_work_mode,
    posted_age_days,
)


def test_experience_range() -> None:
    value = normalize_experience("4-7 Yrs")
    assert value.min == 4
    assert value.max == 7


def test_experience_date_is_not_years() -> None:
    value = normalize_experience("08 Aug")
    assert value.text == "08 Aug"
    assert value.min is None
    assert value.max is None


def test_experience_single_years() -> None:
    value = normalize_experience("5+ Years")
    assert value.min == 5
    assert value.max == 5


def test_experience_filter() -> None:
    exp = Experience(text="3-7 Yrs", min=3, max=7)
    assert experience_matches(exp, 5)
    assert not experience_matches(exp, 8)
    assert experience_matches(exp, None)


def test_salary_lacs() -> None:
    value = normalize_salary("10-20 Lacs PA")
    assert value.min == 1_000_000
    assert value.max == 2_000_000
    assert value.currency == "INR"


def test_salary_not_disclosed() -> None:
    value = normalize_salary("Not disclosed")
    assert value.min is None
    assert value.max is None


def test_work_modes() -> None:
    assert normalize_work_mode("Hybrid") == "hybrid"
    assert normalize_work_mode("Work From Home") == "remote"
    assert normalize_work_mode("Work From Office") == "onsite"
    assert normalize_work_mode("Remote") == "remote"
    assert normalize_work_mode("On-site") == "onsite"


def test_unknown_work_mode_is_none() -> None:
    assert normalize_work_mode("React Developer Persistent Pune Redux CSS") is None


def test_posted_age_and_freshness() -> None:
    assert posted_age_days("Just now") == 0
    assert posted_age_days("4 days ago") == 4
    assert posted_age_days("3+ weeks ago") == 21
    assert freshness_matches("4 days ago", 7)
    assert not freshness_matches("3+ weeks ago", 7)
    assert freshness_matches("anything", None)


def test_employment_type() -> None:
    assert normalize_employment_type("Full Time Permanent") == "full-time"
    assert normalize_employment_type("Contract role") == "contract"
    assert normalize_employment_type("Part-time") == "part-time"
    assert normalize_employment_type("Internship") == "internship"
    assert normalize_employment_type("React Java CSS") is None
