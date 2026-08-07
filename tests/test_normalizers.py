from app.utils.normalizers import normalize_experience, normalize_salary, normalize_work_mode


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
