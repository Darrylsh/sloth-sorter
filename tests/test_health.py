"""Unit tests for health check and dependency reporting."""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app, check_dependencies


def test_check_dependencies_current_env():
    deps = check_dependencies()
    assert isinstance(deps, dict)
    assert "pypdf" in deps
    assert "python-docx" in deps
    assert "Pillow" in deps
    assert "ollama" in deps
    # Current environment should have them installed
    assert deps["pypdf"] is True
    assert deps["python-docx"] is True
    assert deps["Pillow"] is True
    assert deps["ollama"] is True


def test_health_check_endpoint_with_missing_dependency():
    client = TestClient(app)

    # Simulate pypdf missing
    mock_deps = {
        "pypdf": False,
        "python-docx": True,
        "Pillow": True,
        "ollama": True
    }
    with patch("app.main.check_dependencies", return_value=mock_deps):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "pypdf" in data.get("missing_dependencies", [])
        assert data.get("status") in ("degraded", "error")
        assert "pip install" in data.get("fix_command", "")
