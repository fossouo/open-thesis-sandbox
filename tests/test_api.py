import os
import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from main import app

client = TestClient(app)

def test_get_prices_success():
    response = client.get("/api/prices")
    assert response.status_code == 200
    data = response.json()
    assert "dates" in data
    assert "tickers" in data
    assert "prices" in data

def test_get_index_success():
    response = client.get("/")
    assert response.status_code == 200

def test_analyze_success_fr():
    from unittest.mock import MagicMock
    # Setup mock response for LiteLLM (standard MagicMock)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Cette allocation offre une excellente exposition à la croissance des GPU. Néanmoins, elle crée un risque de concentration important sur NVIDIA. Un rééquilibrage vers le cloud est conseillé.",
                    "reasoning_content": "L'utilisateur alloue 100% à NVDA. C'est très concentré."
                }
            }
        ]
    }
    
    # Patch the AsyncClient.post method as an AsyncMock
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        response = client.post(
            "/api/analyze",
            json={
                "weights": {"NVDA": 80.0, "AMD": 20.0},
                "lang": "fr"
            }
        )
        
    assert response.status_code == 200
    data = response.json()
    assert "analysis" in data
    assert "reasoning" in data
    assert "normalized_weights" in data
    assert "NVDA" in data["normalized_weights"]
    
    # Verify values
    assert data["analysis"] == "Cette allocation offre une excellente exposition à la croissance des GPU. Néanmoins, elle crée un risque de concentration important sur NVIDIA. Un rééquilibrage vers le cloud est conseillé."
    assert data["reasoning"] == "L'utilisateur alloue 100% à NVDA. C'est très concentré."
    assert data["normalized_weights"]["NVDA"] == 80.0
    assert data["normalized_weights"]["AMD"] == 20.0

def test_analyze_invalid_language():
    # Testing Pydantic field validator (only 'fr' and 'en' allowed)
    response = client.post(
        "/api/analyze",
        json={
            "weights": {"NVDA": 10.0},
            "lang": "de"  # Invalid language
        }
    )
    assert response.status_code == 422
    assert "lang" in response.text

def test_analyze_zero_weights():
    # Test HTTP 400 when all allocations are zero
    response = client.post(
        "/api/analyze",
        json={
            "weights": {"NVDA": 0.0, "AMD": 0.0},
            "lang": "en"
        }
    )
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "en" in data["detail"]
    assert "greater than 0%" in data["detail"]["en"]
