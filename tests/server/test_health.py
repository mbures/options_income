"""Tests for health and info endpoints.

This module tests the core API endpoints including health checks,
system information, and root endpoint.
"""

import pytest
from fastapi import status
from fastapi.testclient import TestClient


def test_health_endpoint(client_no_db: TestClient):
    """Test GET /health endpoint returns healthy status.

    Args:
        client_no_db: FastAPI test client without database mocking

    Asserts:
        - Response status code is 200
        - Response contains 'status' field
        - Status is 'healthy'
        - Response contains 'timestamp' field
    """
    response = client_no_db.get("/health")

    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "status" in data
    assert data["status"] == "healthy"
    assert "timestamp" in data


def test_root_endpoint(client_no_db: TestClient):
    """Test GET / endpoint returns welcome message.

    Args:
        client_no_db: FastAPI test client without database mocking

    Asserts:
        - Response status code is 200
        - Response contains welcome message
        - Response contains version information
        - Response contains links to documentation endpoints
    """
    response = client_no_db.get("/")

    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "message" in data
    assert "Wheel Strategy API" in data["message"]
    assert "version" in data
    assert "docs" in data
    assert data["docs"] == "/docs"
    assert "health" in data
    assert data["health"] == "/health"
    assert "api" in data
    assert data["api"] == "/api/v1/info"


def test_api_v1_info_endpoint(client_no_db: TestClient):
    """Test GET /api/v1/info endpoint returns system information.

    Args:
        client_no_db: FastAPI test client without database mocking

    Asserts:
        - Response status code is 200
        - Response contains app_name
        - Response contains version
        - Response contains status
        - Response contains database_connected boolean
        - Response contains timestamp
    """
    response = client_no_db.get("/api/v1/info")

    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "app_name" in data
    assert data["app_name"] == "Wheel Strategy API"
    assert "version" in data
    assert data["version"] == "1.0.0"
    assert "status" in data
    assert data["status"] == "running"
    assert "database_connected" in data
    assert isinstance(data["database_connected"], bool)
    assert "timestamp" in data


def test_openapi_docs_available(client_no_db: TestClient):
    """Test that OpenAPI documentation is available.

    Args:
        client_no_db: FastAPI test client without database mocking

    Asserts:
        - GET /docs redirects to Swagger UI (200 or 307)
        - GET /openapi.json returns OpenAPI schema
        - OpenAPI schema contains expected structure
    """
    # Test that docs endpoint exists
    response = client_no_db.get("/docs", follow_redirects=False)
    assert response.status_code in [status.HTTP_200_OK, status.HTTP_307_TEMPORARY_REDIRECT]

    # Test OpenAPI schema
    response = client_no_db.get("/openapi.json")
    assert response.status_code == status.HTTP_200_OK

    schema = response.json()
    assert "openapi" in schema
    assert "info" in schema
    assert "paths" in schema
    assert "/health" in schema["paths"]
    assert "/api/v1/info" in schema["paths"]


def test_cors_headers_present(client_no_db: TestClient):
    """Test that CORS headers are properly configured.

    Args:
        client_no_db: FastAPI test client without database mocking

    Asserts:
        - Response includes CORS headers for allowed origins
    """
    # Make a request with Origin header
    response = client_no_db.get(
        "/health",
        headers={"Origin": "http://localhost:3000"}
    )

    assert response.status_code == status.HTTP_200_OK
    # CORS headers should be present in response
    assert "access-control-allow-origin" in response.headers


def test_health_endpoint_response_structure(client_no_db: TestClient):
    """Test that health endpoint response matches expected schema.

    Args:
        client_no_db: FastAPI test client without database mocking

    Asserts:
        - Response structure matches HealthResponse model
        - Timestamp is in valid ISO format
        - Scheduler running status is included
    """
    response = client_no_db.get("/health")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    # Verify structure (scheduler_running is optional but should be present)
    expected_keys = {"status", "timestamp", "scheduler_running"}
    assert set(data.keys()) == expected_keys

    # Verify types
    assert isinstance(data["status"], str)
    assert isinstance(data["timestamp"], str)
    assert isinstance(data["scheduler_running"], bool)

    # Verify timestamp is valid ISO format
    from datetime import datetime
    try:
        datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
    except ValueError:
        pytest.fail("Timestamp is not in valid ISO format")


def test_info_endpoint_response_structure(client_no_db: TestClient):
    """Test that info endpoint response matches expected schema.

    Args:
        client_no_db: FastAPI test client without database mocking

    Asserts:
        - Response structure matches InfoResponse model
        - All required fields are present with correct types
    """
    response = client_no_db.get("/api/v1/info")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    # Verify all required fields present
    required_fields = {
        "app_name",
        "version",
        "status",
        "database_connected",
        "timestamp",
    }
    assert set(data.keys()) == required_fields

    # Verify types
    assert isinstance(data["app_name"], str)
    assert isinstance(data["version"], str)
    assert isinstance(data["status"], str)
    assert isinstance(data["database_connected"], bool)
    assert isinstance(data["timestamp"], str)

    # Verify timestamp is valid ISO format
    from datetime import datetime
    try:
        datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
    except ValueError:
        pytest.fail("Timestamp is not in valid ISO format")
