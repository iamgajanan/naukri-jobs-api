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

    # Do not interpret dates such as "08 Aug" as eight years of experience.
    return Experience(text=text, min=None, max=None)


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
