import pytest
import httpx
from fastapi.testclient import TestClient
from unittest.mock import patch
from main import app

client = TestClient(app)

def test_api_robustness_timeout():
    # Patch HTTP call to raise httpx.TimeoutException
    with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Request timed out")):
        response = client.post(
            "/api/analyze",
            json={
                "weights": {"NVDA": 100.0},
                "lang": "fr"
            }
        )
        
    # Verify that we return a 504 Gateway Timeout
    assert response.status_code == 504
    data = response.json()
    assert "detail" in data
    assert "fr" in data["detail"]
    assert "en" in data["detail"]
    assert "timeout" in data["detail"]["en"]

def test_api_robustness_connection_refused():
    # Patch HTTP call to raise httpx.ConnectError (offline server simulator)
    with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("Connection refused")):
        response = client.post(
            "/api/analyze",
            json={
                "weights": {"NVDA": 100.0},
                "lang": "en"
            }
        )
        
    # Verify that we return a 503 Service Unavailable
    assert response.status_code == 503
    data = response.json()
    assert "detail" in data
    assert "fr" in data["detail"]
    assert "en" in data["detail"]
    assert "unreachable" in data["detail"]["en"]

def test_api_robustness_internal_server_error():
    # Patch HTTP call to raise a generic Exception
    with patch("httpx.AsyncClient.post", side_effect=Exception("Database crash on backend")):
        response = client.post(
            "/api/analyze",
            json={
                "weights": {"NVDA": 100.0},
                "lang": "fr"
            }
        )
        
    # Verify that we return a 500 Internal Server Error
    assert response.status_code == 500
    data = response.json()
    assert "detail" in data
    assert "fr" in data["detail"]
    assert "en" in data["detail"]
    assert "Database crash" in data["detail"]["fr"] or "Database crash" in data["detail"]["en"]
