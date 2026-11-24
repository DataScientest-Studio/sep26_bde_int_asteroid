from fastapi.testclient import TestClient
from src.api.main import asteroid

client = TestClient(asteroid)

def test_openapi_lists_all_routes():
    """If any import or route is broken, this fails first."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert len(response.json()["paths"]) > 10

def test_health_responds():
    response = client.get("/health")
    assert response.status_code == 200
    assert "database" in response.json()

def test_metrics_are_exposed():
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text

def test_unknown_path_returns_404():
    response = client.get("/no-such-endpoint")
    assert response.status_code == 404