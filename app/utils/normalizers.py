import re

from app.schemas.jobs import Experience, Salary


def normalize_experience(value: str | None) -> Experience:
    if not value:
        return Experience()

    numbers = [int(n) for n in re.findall(r"\d+", value)]
    minimum = numbers[0] if numbers else None
    maximum = numbers[1] if len(numbers) > 1 else minimum
    return Experience(text=value.strip(), min=minimum, max=maximum)


def _to_rupees(number: float, unit: str | None) -> int:
    unit = (unit or "").lower()
    if "crore" in unit or unit in {"cr", "crores"}:
        return int(number * 10_000_000)
    if "lac" in unit or "lakh" in unit:
        return int(number * 100_000)
    return int(number)


def normalize_salary(value: str | None) -> Salary:
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


def normalize_work_mode(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.strip().lower()
    if "hybrid" in lowered:
        return "hybrid"
    if "remote" in lowered or "work from home" in lowered or "wfh" in lowered:
        return "remote"
    if "office" in lowered or "onsite" in lowered or "on-site" in lowered:
        return "onsite"
    return lowered
