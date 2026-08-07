"""Pre-Railway live verification and timing benchmark.

Covers every meaningful filter PRESENCE combination supported by the API:
keyword/location are the base search; optional filters are experience,
freshness and work_mode. For 3 optional filters this gives 2^3 = 8
presence combinations. Representative boundary/value cases, pagination,
limits up to 100, data quality and cache behavior are tested separately.

This deliberately avoids the full Cartesian product of every numeric value,
which would generate hundreds of unnecessary live Naukri requests.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8000/v1/jobs/search"

CASES = [
    # Baseline / keyword / location / pagination / limits
    ("baseline", {"keyword": "developer", "location": "pune", "page": 1, "limit": 20}),
    ("keyword-react", {"keyword": "react", "location": "pune", "page": 1, "limit": 5}),
    ("java-bangalore", {"keyword": "java", "location": "bangalore", "page": 1, "limit": 5}),
    ("python-hyderabad", {"keyword": "python", "location": "hyderabad", "page": 1, "limit": 5}),
    ("page-2", {"keyword": "react", "location": "pune", "page": 2, "limit": 5}),
    ("page-3", {"keyword": "react", "location": "pune", "page": 3, "limit": 5}),
    ("limit-50", {"keyword": "react", "location": "pune", "page": 1, "limit": 50}),
    ("limit-100", {"keyword": "react", "location": "pune", "page": 1, "limit": 100}),

    # All 2^3 optional-filter PRESENCE combinations.
    # 000 is the baseline above.
    ("exp-only", {"keyword": "developer", "location": "pune", "experience": 5, "page": 1, "limit": 10}),
    ("fresh-only", {"keyword": "developer", "location": "pune", "freshness": 7, "page": 1, "limit": 10}),
    ("mode-only-remote", {"keyword": "developer", "location": "pune", "work_mode": "remote", "page": 1, "limit": 10}),
    ("exp+fresh", {"keyword": "developer", "location": "pune", "experience": 5, "freshness": 7, "page": 1, "limit": 10}),
    ("exp+mode", {"keyword": "developer", "location": "pune", "experience": 5, "work_mode": "remote", "page": 1, "limit": 10}),
    ("fresh+mode", {"keyword": "developer", "location": "pune", "freshness": 7, "work_mode": "remote", "page": 1, "limit": 10}),
    ("exp+fresh+mode", {"keyword": "developer", "location": "pune", "experience": 5, "freshness": 7, "work_mode": "remote", "page": 1, "limit": 10}),

    # Work-mode values
    ("mode-hybrid", {"keyword": "developer", "location": "pune", "work_mode": "hybrid", "page": 1, "limit": 10}),
    ("mode-onsite", {"keyword": "developer", "location": "pune", "work_mode": "onsite", "page": 1, "limit": 10}),

    # Representative filter boundaries/values
    ("exp-0", {"keyword": "developer", "location": "pune", "experience": 0, "page": 1, "limit": 5}),
    ("exp-3", {"keyword": "developer", "location": "pune", "experience": 3, "page": 1, "limit": 5}),
    ("exp-10", {"keyword": "developer", "location": "pune", "experience": 10, "page": 1, "limit": 5}),
    ("fresh-1", {"keyword": "developer", "location": "pune", "freshness": 1, "page": 1, "limit": 5}),
    ("fresh-30", {"keyword": "developer", "location": "pune", "freshness": 30, "page": 1, "limit": 5}),
]


def request(params):
    url = BASE + "?" + urllib.parse.urlencode(params)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=300) as response:
            payload = json.loads(response.read().decode())
            return response.headers.get("X-Data-Source"), payload, time.perf_counter() - started
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        elapsed = time.perf_counter() - started
        raise AssertionError("HTTP {} after {:.3f}s: {}".format(exc.code, elapsed, body))
    except Exception as exc:
        elapsed = time.perf_counter() - started
        raise AssertionError("{} after {:.3f}s: {}".format(type(exc).__name__, elapsed, exc))


def validate(params, data):
    assert data["status"] == "success", data
    jobs = data["jobs"]
    assert len(jobs) <= params["limit"]
    ids = [job["id"] for job in jobs]
    urls = [job["job_url"] for job in jobs]
    assert len(ids) == len(set(ids)), "duplicate job ids returned"
    assert len(urls) == len(set(urls)), "duplicate job URLs returned"
    for job in jobs:
        assert job["id"], "missing id"
        assert job["title"], "missing title"
        assert job["company"], "missing company"
        assert job["job_url"].startswith("https://www.naukri.com/"), "invalid Naukri URL"
        assert job["source"] == "naukri"
        assert job["work_mode"] in (None, "remote", "hybrid", "onsite")
        assert job["employment_type"] in (None, "full-time", "part-time", "contract", "internship")
    if params.get("experience") is not None:
        requested = params["experience"]
        for job in jobs:
            exp = job["experience"]
            assert exp["min"] is not None and exp["max"] is not None
            assert exp["min"] <= requested <= exp["max"], "experience mismatch"
    if params.get("freshness") is not None:
        assert all(job.get("posted_at") for job in jobs), "freshness result missing posted_at"
    if params.get("work_mode"):
        assert all(job["work_mode"] == params["work_mode"] for job in jobs), "work mode mismatch"


def invalid_case(name, params, expected=422):
    url = BASE + "?" + urllib.parse.urlencode(params)
    started = time.perf_counter()
    try:
        urllib.request.urlopen(url, timeout=30)
        return name, False, "expected HTTP {}, got success".format(expected), time.perf_counter() - started
    except urllib.error.HTTPError as exc:
        return name, exc.code == expected, "HTTP {}".format(exc.code), time.perf_counter() - started


started_all = time.perf_counter()
results = []
failures = []
for name, case in CASES:
    try:
        source, payload, seconds = request(case)
        validate(case, payload)
        results.append((name, "PASS", source or "?", len(payload["jobs"]), seconds, ""))
        print("PASS {:20s} source={:12s} jobs={:3d} time={:.3f}s".format(name, source or "?", len(payload["jobs"]), seconds))
    except Exception as exc:
        message = str(exc)
        failures.append((name, message))
        results.append((name, "FAIL", "-", 0, 0.0, message))
        print("FAIL {:20s} {}".format(name, message))

# Validation boundaries should fail before any upstream collection.
INVALID = [
    ("missing-keyword", {}),
    ("page-0", {"keyword": "react", "page": 0}),
    ("limit-0", {"keyword": "react", "limit": 0}),
    ("limit-101", {"keyword": "react", "limit": 101}),
    ("experience--1", {"keyword": "react", "experience": -1}),
    ("experience-51", {"keyword": "react", "experience": 51}),
    ("freshness-0", {"keyword": "react", "freshness": 0}),
    ("freshness-31", {"keyword": "react", "freshness": 31}),
    ("bad-work-mode", {"keyword": "react", "work_mode": "anywhere"}),
]
for name, params in INVALID:
    name, ok, detail, seconds = invalid_case(name, params)
    if ok:
        print("PASS {:20s} validation={} time={:.3f}s".format(name, detail, seconds))
    else:
        failures.append((name, detail))
        print("FAIL {:20s} {}".format(name, detail))

# Cache: unique query to make first request live, immediate repeat should cache.
cache_case = {"keyword": "react cache benchmark", "location": "pune", "page": 1, "limit": 20}
try:
    source1, payload1, live_time = request(cache_case)
    validate(cache_case, payload1)
    source2, payload2, cache_time = request(cache_case)
    validate(cache_case, payload2)
    assert source2 == "cache", "expected repeated request to use cache, got {!r}".format(source2)
    assert payload1["jobs"] == payload2["jobs"], "cached payload differs"
    print("PASS cache-repeat         first={} second={} first={:.3f}s cache={:.3f}s".format(source1, source2, live_time, cache_time))
except Exception as exc:
    failures.append(("cache-repeat", str(exc)))
    print("FAIL cache-repeat         {}".format(exc))

total_time = time.perf_counter() - started_all
passed_live = sum(1 for r in results if r[1] == "PASS")
print("\nSUMMARY")
for name, status, source, count, seconds, error in results:
    if status == "PASS":
        print("{:<20} PASS source={:<10} jobs={:<3} {:.3f}s".format(name, source, count, seconds))
    else:
        print("{:<20} FAIL {}".format(name, error))
print("\nLIVE CASES: {} passed / {}".format(passed_live, len(CASES)))
print("FAILURES: {}".format(len(failures)))
print("TOTAL SUITE TIME: {:.3f}s ({:.2f} min)".format(total_time, total_time / 60.0))
if failures:
    print("LIVE VERIFICATION HAS FAILURES")
    for name, error in failures:
        print("- {}: {}".format(name, error))
    raise SystemExit(1)
print("LIVE VERIFICATION PASSED")
