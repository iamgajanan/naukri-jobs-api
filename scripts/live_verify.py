"""Run only from an environment where anonymous Naukri browsing works.

Usage: NAUKRI_HEADLESS=false python scripts/live_verify.py
"""
import json
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8000/v1/jobs/search"

CASES = [
    {"keyword": "react", "location": "pune", "page": 1, "limit": 5},
    {"keyword": "react", "location": "pune", "page": 2, "limit": 20},
    {"keyword": "python", "location": "bangalore", "experience": 3, "freshness": 7, "page": 1, "limit": 20},
]


def request(params):
    url = BASE + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=180) as response:
        return response.headers.get("X-Data-Source"), json.loads(response.read().decode())


def validate(params, data):
    assert data["status"] == "success"
    assert len(data["jobs"]) <= params["limit"]
    ids = [job["id"] for job in data["jobs"]]
    assert len(ids) == len(set(ids)), "duplicate job ids returned"
    for job in data["jobs"]:
        assert job["title"]
        assert job["job_url"].startswith("https://www.naukri.com/")
        assert job["work_mode"] in (None, "remote", "hybrid", "onsite")
    if params.get("experience") is not None:
        requested = params["experience"]
        for job in data["jobs"]:
            exp = job["experience"]
            assert exp["min"] <= requested <= exp["max"]


for case in CASES:
    source, payload = request(case)
    validate(case, payload)
    print("PASS", case, "source=", source, "jobs=", len(payload["jobs"]))

# Exact repeat must be served from cache.
source, payload = request(CASES[0])
assert source == "cache", "expected repeated request to use cache, got %r" % source
print("PASS repeated request source=cache")
print("LIVE VERIFICATION PASSED")
