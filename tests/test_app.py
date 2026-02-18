"""Tests for the system dashboard."""

import pytest
from fastapi.testclient import TestClient

from dashboard.app import app


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthRoutes:
    def test_health_page(self, client):
        resp = client.get("/health/")
        assert resp.status_code == 200
        assert "System Health" in resp.text

    def test_health_api(self, client):
        resp = client.get("/health/api")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_repos" in data
        assert "organs" in data


class TestRegistryRoutes:
    def test_registry_page(self, client):
        resp = client.get("/registry/")
        assert resp.status_code == 200
        assert "Registry Browser" in resp.text

    def test_registry_filter(self, client):
        resp = client.get("/registry/?organ=ORGAN-I")
        assert resp.status_code == 200


class TestGraphRoutes:
    def test_graph_page(self, client):
        resp = client.get("/graph/")
        assert resp.status_code == 200
        assert "Dependency Graph" in resp.text

    def test_graph_api(self, client):
        resp = client.get("/graph/api")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data


class TestSoakRoutes:
    def test_soak_page(self, client):
        resp = client.get("/soak/")
        assert resp.status_code == 200
        assert "VIGILIA" in resp.text


class TestEssayRoutes:
    def test_essays_page(self, client):
        resp = client.get("/essays/")
        assert resp.status_code == 200
        assert "Essays" in resp.text


class TestOmegaRoutes:
    def test_omega_page(self, client):
        resp = client.get("/omega/")
        assert resp.status_code == 200
        assert "Omega Scorecard" in resp.text

    def test_omega_has_criteria(self, client):
        resp = client.get("/omega/")
        assert "MET" in resp.text or "NOT MET" in resp.text


class TestRootRedirect:
    def test_root_redirects(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 307
        assert "/health/" in resp.headers["location"]
