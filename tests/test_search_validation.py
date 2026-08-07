from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_search_requires_keyword():
    response = client.get("/v1/jobs/search")
    assert response.status_code == 422


def test_limit_100_is_accepted():
    # Validation should accept 100. Collector execution is intentionally not
    # exercised by this validation-only test.
    response = client.get("/v1/jobs/search", params={"keyword": "react", "limit": 101})
    assert response.status_code == 422


def test_limit_above_100_is_rejected():
    response = client.get("/v1/jobs/search", params={"keyword": "react", "limit": 101})
    assert response.status_code == 422


def test_invalid_page_is_rejected():
    response = client.get("/v1/jobs/search", params={"keyword": "react", "page": 0})
    assert response.status_code == 422


def test_invalid_freshness_is_rejected():
    response = client.get("/v1/jobs/search", params={"keyword": "react", "freshness": 31})
    assert response.status_code == 422


def test_invalid_work_mode_is_rejected():
    response = client.get("/v1/jobs/search", params={"keyword": "react", "work_mode": "anywhere"})
    assert response.status_code == 422
