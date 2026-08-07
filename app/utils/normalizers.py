import re
from typing import Optional

from app.schemas.jobs import Experience, Salary


_EXPERIENCE_RANGE = re.compile(r"\b(\d{1,2})\s*(?:-|to)\s*(\d{1,2})\s*(?:yrs?|years?)\b", re.I)
_EXPERIENCE_SINGLE = re.compile(r"\b(\d{1,2})\+?\s*(?:yrs?|years?)\b", re.I)


def normalize_experience(value: Optional[str]) -> Experience:
    if not value:
        return Experience()
    text = value.strip()
    match = _EXPERIENCE_RANGE.search(text)
    if match:
        return Experience(text=text, min=int(match.group(1)), max=int(match.group(2)))
    match = _EXPERIENCE_SINGLE.search(text)
    if match:
        years = int(match.group(1))
        return Experience(text=text, min=years, max=years)
    return Experience(text=text, min=None, max=None)


def experience_matches(experience: Experience, requested: Optional[int]) -> bool:
    if requested is None:
        return True
    if experience.min is None or experience.max is None:
        return False
    return experience.min <= requested <= experience.max


def _to_rupees(number: float, unit: Optional[str]) -> int:
    unit = (unit or "").lower()
    if "crore" in unit or unit in {"cr", "crores"}:
        return int(number * 10_000_000)
    if "lac" in unit or "lakh" in unit:
        return int(number * 100_000)
    return int(number)


def normalize_salary(value: Optional[str]) -> Salary:
    if not value:
        return Salary()
    text = value.strip()
    lowered = text.lower()
    if "not disclosed" in lowered:
        return Salary(text=text, min=None, max=None, currency="INR")
    unit_match = re.search(r"(lacs?|lakhs?|crores?|cr)\b", lowered)
    unit = unit_match.group(1) if unit_match else None
    numbers = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", lowered)]
    minimum = _to_rupees(numbers[0], unit) if numbers else None
    maximum = _to_rupees(numbers[1], unit) if len(numbers) > 1 else minimum
    return Salary(text=text, min=minimum, max=maximum, currency="INR")


def normalize_work_mode(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    lowered = " ".join(value.strip().lower().split())
    if re.search(r"\bhybrid\b", lowered):
        return "hybrid"
    if re.search(r"\bremote\b|work\s+from\s+home|\bwfh\b", lowered):
        return "remote"
    if re.search(r"\bonsite\b|\bon-site\b|work\s+from\s+office|\bwfo\b", lowered):
        return "onsite"
    return None


def normalize_employment_type(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    lowered = " ".join(value.lower().split())
    if "internship" in lowered or re.search(r"\bintern\b", lowered):
        return "internship"
    if "contract" in lowered:
        return "contract"
    if "part time" in lowered or "part-time" in lowered:
        return "part-time"
    if "full time" in lowered or "full-time" in lowered or "permanent" in lowered:
        return "full-time"
    return None


def posted_age_days(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    lowered = " ".join(value.strip().lower().split())
    if lowered in {"just now", "today", "few hours ago", "few minutes ago"}:
        return 0
    if "hour" in lowered or "minute" in lowered:
        return 0
    match = re.search(r"(\d+)\s*days?\s*ago", lowered)
    if match:
        return int(match.group(1))
    match = re.search(r"(\d+)\+?\s*weeks?\s*ago", lowered)
    if match:
        return int(match.group(1)) * 7
    match = re.search(r"(\d+)\+?\s*months?\s*ago", lowered)
    if match:
        return int(match.group(1)) * 30
    return None


def freshness_matches(posted_at: Optional[str], freshness_days: Optional[int]) -> bool:
    if freshness_days is None:
        return True
    age = posted_age_days(posted_at)
    return age is not None and age <= freshness_days
