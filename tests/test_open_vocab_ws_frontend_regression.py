"""
Phase 26 — Frontend WebSocket regression tests.

STATUS: SKIPPED — frontend test infrastructure is absent.

The frontend (frontend/package.json) has no test runner configured:
no jest, no vitest, no @testing-library/react.
All scripts are: dev, build, lint, preview.

Backend-side regressions for the WebSocket service are covered in:
  tests/test_open_vocab_streaming.py
  tests/test_open_vocab_lifecycle.py

To add real frontend tests in a future phase:
  1. npm install --save-dev vitest @testing-library/react jsdom
  2. Add "test": "vitest" to package.json scripts
  3. Write useOpenVocabStream.test.js and OpenVocabStatusPanel.test.jsx

All tests in this file are marked skip so the suite stays green.
"""
import pytest


@pytest.mark.skip(reason="No frontend test runner (jest/vitest) configured in frontend/package.json")
def test_use_open_vocab_stream_connects():
    """Would test: hook connects to /ws/open-vocab and sets connected=true."""


@pytest.mark.skip(reason="No frontend test runner (jest/vitest) configured in frontend/package.json")
def test_use_open_vocab_stream_falls_back_after_disconnect():
    """Would test: transport changes to polling_fallback after WS close."""


@pytest.mark.skip(reason="No frontend test runner (jest/vitest) configured in frontend/package.json")
def test_open_vocab_status_panel_renders_threat_badge():
    """Would test: LiveThreatBadge renders with correct risk-level color."""
