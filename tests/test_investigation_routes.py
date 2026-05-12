from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_investigation_routes_registered():
    routes = [r.path for r in app.routes]
    assert any("investigation" in r for r in routes)


def test_path_reconstruction_endpoint_exists():
    resp = client.post("/api/investigation/path-reconstruction", json={})
    assert resp.status_code != 404


def test_hypotheses_endpoint_exists():
    resp = client.get("/api/investigation/hypotheses")
    assert resp.status_code != 404


def test_camera_graph_endpoint_exists():
    resp = client.get("/api/investigation/cameras/graph")
    assert resp.status_code != 404


def test_accept_endpoint_exists():
    resp = client.post("/api/investigation/hypotheses/hyp_test/accept")
    assert resp.status_code != 404


def test_reject_endpoint_exists():
    resp = client.post("/api/investigation/hypotheses/hyp_test/reject")
    assert resp.status_code != 404


def test_inconclusive_endpoint_exists():
    resp = client.post("/api/investigation/hypotheses/hyp_test/inconclusive")
    assert resp.status_code != 404


def test_case_timeline_endpoint_exists():
    resp = client.get("/api/investigation/cases/case_test/timeline")
    assert resp.status_code != 404
