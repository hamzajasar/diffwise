from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["content-type"] == "application/json"


# Negative cases: the endpoint should only accept what it's meant to.


def test_health_rejects_post():
    response = client.post("/health")

    assert response.status_code == 405  # Method Not Allowed


def test_unknown_path_returns_404():
    response = client.get("/does-not-exist")

    assert response.status_code == 404
