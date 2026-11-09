from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_check_returns_service_metadata() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "Illinois Chat API",
        "version": "0.1.0",
        "environment": "development",
    }


def test_openapi_document_is_available() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/api/v1/health" in response.json()["paths"]
