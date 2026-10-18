"""Security-focused tests."""

import hashlib
import hmac
import json
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import app
from app.services.github_client import verify_webhook_signature

WEBHOOK_SECRET = "test-webhook-secret"


@pytest.fixture
async def client():
    """Client with webhook secret properly configured."""
    patched = Settings(
        openai_api_key="sk-test-fake",
        github_token="ghp_test_fake",
        github_webhook_secret=WEBHOOK_SECRET,
    )
    with patch("app.api.routes.settings", patched):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def test_webhook_rejects_missing_signature(client):
    resp = await client.post(
        "/webhook/github",
        content=b'{"action":"opened"}',
        headers={"x-github-event": "pull_request"},
    )
    assert resp.status_code == 401


async def test_webhook_rejects_wrong_signature(client):
    resp = await client.post(
        "/webhook/github",
        content=b'{"action":"opened"}',
        headers={
            "x-github-event": "pull_request",
            "x-hub-signature-256": "sha256=definitely-wrong",
        },
    )
    assert resp.status_code == 401


async def test_webhook_ignores_non_pr_events(client):
    payload = b'{"action":"created"}'
    sig = "sha256=" + hmac.new(WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    resp = await client.post(
        "/webhook/github",
        content=payload,
        headers={
            "x-github-event": "issues",
            "x-hub-signature-256": sig,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


async def test_webhook_ignores_non_actionable_pr_events(client):
    payload = json.dumps({"action": "closed"}).encode()
    sig = "sha256=" + hmac.new(WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    resp = await client.post(
        "/webhook/github",
        content=payload,
        headers={
            "x-github-event": "pull_request",
            "x-hub-signature-256": sig,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


async def test_review_payload_size_limit(client):
    huge_diff = "+" * 300_000
    resp = await client.post("/review", json={
        "diff": huge_diff,
        "file_path": "big.py",
    })
    assert resp.status_code == 422


def test_webhook_signature_timing_safe():
    secret = "test"
    payload = b"data"
    sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert verify_webhook_signature(payload, sig, secret) is True


async def test_webhook_no_secret_configured():
    patched = Settings(
        openai_api_key="sk-test",
        github_token="ghp_test",
        github_webhook_secret="",
    )
    with patch("app.api.routes.settings", patched):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post(
                "/webhook/github",
                content=b'{}',
                headers={"x-github-event": "pull_request"},
            )
            assert resp.status_code == 503
