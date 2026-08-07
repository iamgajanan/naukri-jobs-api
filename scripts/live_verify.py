"""Comprehensive live verification and timing benchmark.

Start the API first with NAUKRI_HEADLESS=false, then run this script.
Each case is isolated: one failure does not abort the remaining suite.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8000/v1/jobs/search"

CASES = [
    ("react-pune", {"keyword": "react", "location": "pune", "page": 1, "limit": 5}),
    ("java-bangalore", {"keyword": "java", "location": "bangalore", "page": 1, "limit": 5}),
    ("python-hyderabad", {"keyword": "python", "location": "hyderabad", "page": 1, "limit": 5}),
    ("frontend-pune", {"keyword": "frontend developer", "location": "pune", "page": 1, "limit": 5}),
    ("page-2", {"keyword": "react", "location": "pune", "page": 2, "limit": 5}),
    ("page-3", {"keyword": "react", "location": "pune", "page": 3, "limit": 5}),
    ("limit-20", {"keyword": "react", "location": "pune", "page": 1, "limit": 20}),
    ("limit-50", {"keyword": "react", "location": "pune", "page": 1, "limit": 50}),
    ("experience-5", {"keyword": "software engineer", "location": "pune", "experience": 5, "page": 1, "limit": 10}),
    ("freshness-7", {"keyword": "react", "location": "pune", "freshness": 7, "page": 1, "limit": 10}),
    ("remote", {"keyword": "developer", "location": "pune", "work_mode": "remote", "page": 1, "limit": 10}),
    ("combined", {"keyword": "developer", "location": "pune", "experience": 5, "freshness": 7, "page": 1, "limit": 10}),
]


def request(params):
    url = BASE + "?" + urllib.parse.urlencode(params)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=240) as response:
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
        assert job["id"] and job["title"] and job["company"]
        assert job["job_url"].startswith("https://www.naukri.com/")
        assert job["work_mode"] in (None, "remote", "hybrid", "onsite")
        assert job["employment_type"] in (None, "full-time", "part-time", "contract", "internship")
    if params.get("experience") is not None:
        requested = params["experience"]
        for job in jobs:
            exp = job["experience"]
            assert exp["min"] is not None and exp["max"] is not None
            assert exp["min"] <= requested <= exp["max"]
    if params.get("freshness") is not None:
        # Server-side freshness filtering is tested by the normalizer unit tests;
        # here we at least require every returned live item to expose posted_at.
        assert all(job.get("posted_at") for job in jobs)
    if params.get("work_mode"):
        assert all(job["work_mode"] == params["work_mode"] for job in jobs)


results = []
failures = []
for name, case in CASES:
    try:
        source, payload, seconds = request(case)
        validate(case, payload)
        results.append((name, "PASS", source or "?", len(payload["jobs"]), seconds, ""))
        print("PASS {:20s} source={:12s} jobs={:2d} time={:.3f}s".format(name, source or "?", len(payload["jobs"]), seconds))
    except Exception as exc:
        message = str(exc)
        failures.append((name, message))
        results.append((name, "FAIL", "-", 0, 0.0, message))
        print("FAIL {:20s} {}".format(name, message))

# Cache verification is also isolated so the final report is always printed.
cache_case = {"keyword": "react cache verification", "location": "pune", "page": 1, "limit": 5}
try:
    source1, payload1, live_time = request(cache_case)
    validate(cache_case, payload1)
    source2, payload2, cache_time = request(cache_case)
    validate(cache_case, payload2)
    assert source1 in ("live", "cache"), source1
    assert source2 == "cache", "expected repeated request to use cache, got {!r}".format(source2)
    assert payload1["jobs"] == payload2["jobs"], "cached payload differs from original"
    print("PASS cache-repeat         first={} second={} live={:.3f}s cache={:.3f}s".format(source1, source2, live_time, cache_time))
except Exception as exc:
    failures.append(("cache-repeat", str(exc)))
    print("FAIL cache-repeat         {}".format(exc))

print("\nSUMMARY")
for name, status, source, count, seconds, error in results:
    if status == "PASS":
        print("{:<20} PASS source={:<10} jobs={:<3} {:.3f}s".format(name, source, count, seconds))
    else:
        print("{:<20} FAIL {}".format(name, error))

print("\nTOTAL: {} passed, {} failed".format(len(CASES) - len([f for f in failures if f[0] != "cache-repeat"]), len(failures)))
if failures:
    print("LIVE VERIFICATION HAS FAILURES")
    for name, error in failures:
        print("- {}: {}".format(name, error))
    raise SystemExit(1)

print("LIVE VERIFICATION PASSED")
