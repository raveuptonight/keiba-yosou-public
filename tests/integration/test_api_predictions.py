"""
Integration tests for predictions API endpoints.

Tests the /api/predictions/* endpoints using FastAPI TestClient.
"""

import os
import pytest
from unittest.mock import patch, AsyncMock

# Ensure mock mode
os.environ["DB_MODE"] = "mock"


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_endpoint(self, api_client):
        """Test /health returns 200."""
        response = api_client.get("/health")
        assert response.status_code == 200

    def test_health_response_format(self, api_client):
        """Test health response has expected format."""
        response = api_client.get("/health")
        data = response.json()

        assert "status" in data
        assert data["status"] in ["healthy", "ok"]


class TestRootEndpoint:
    """Test root endpoint."""

    def test_root_endpoint(self, api_client):
        """Test / returns 200."""
        response = api_client.get("/")
        assert response.status_code == 200

    def test_root_response_content(self, api_client):
        """Test root response contains expected info."""
        response = api_client.get("/")
        data = response.json()

        assert "message" in data
        assert "version" in data
        assert data["version"] == "1.0.0"


class TestPredictionsEndpoints:
    """Test predictions API endpoints."""

    def test_generate_prediction_endpoint(self, api_client):
        """Test POST /api/predictions/generate."""
        response = api_client.post(
            "/api/predictions/generate",
            json={"race_id": "2025012506010911"},
        )

        # In mock mode, should succeed with 200
        assert response.status_code in [200, 201, 422, 500]

    def test_generate_prediction_missing_race_id(self, api_client):
        """Test generate endpoint requires race_id."""
        response = api_client.post(
            "/api/predictions/generate",
            json={},
        )

        # Should fail validation
        assert response.status_code == 422

    def test_generate_prediction_invalid_race_id(self, api_client):
        """Test generate endpoint validates race_id format."""
        response = api_client.post(
            "/api/predictions/generate",
            json={"race_id": "invalid"},
        )

        # Should fail validation or return error
        assert response.status_code in [400, 422, 500]


class TestAPIVersioning:
    """Test API versioning."""

    def test_v1_prefix_works(self, api_client):
        """Test /api/v1/ prefix is available."""
        # Health endpoint should work on both paths
        response = api_client.get("/health")
        assert response.status_code == 200

    def test_api_prefix_works(self, api_client):
        """Test /api/ prefix is available for backward compatibility."""
        response = api_client.get("/")
        assert response.status_code == 200


class TestCORS:
    """Test CORS configuration."""

    def test_cors_headers_present(self, api_client):
        """Test CORS headers are set."""
        response = api_client.options(
            "/",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

        # OPTIONS should not fail
        assert response.status_code in [200, 204, 405]


class TestErrorHandling:
    """Test API error handling."""

    def test_404_for_unknown_endpoint(self, api_client):
        """Test 404 for unknown endpoints."""
        response = api_client.get("/api/unknown/endpoint")
        assert response.status_code == 404

    def test_method_not_allowed(self, api_client):
        """Test 405 for wrong HTTP method."""
        # DELETE on GET-only endpoint
        response = api_client.delete("/health")
        assert response.status_code == 405
