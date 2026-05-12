from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app.main import app


client = TestClient(app, raise_server_exceptions=False)


def test_path_reconstruction_requires_investigation_write():
    resp = client.post("/api/investigation/path-reconstruction", json={})
    assert resp.status_code in (401, 403, 422)


def test_list_hypotheses_requires_investigation_read():
    resp = client.get("/api/investigation/hypotheses")
    assert resp.status_code in (401, 403)


def test_camera_graph_requires_investigation_read():
    resp = client.get("/api/investigation/cameras/graph")
    assert resp.status_code in (401, 403)


def test_case_timeline_requires_investigation_read():
    resp = client.get("/api/investigation/cases/case_001/timeline")
    assert resp.status_code in (401, 403)


def test_unauthenticated_cannot_write_investigation():
    resp = client.post(
        "/api/investigation/path-reconstruction",
        json={"case_id": "case_test"},
    )
    assert resp.status_code in (401, 403, 422)
