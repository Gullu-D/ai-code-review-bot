import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_review_validation_missing_diff(client):
    resp = await client.post("/review", json={"file_path": "test.py"})
    assert resp.status_code == 422


async def test_review_validation_empty_diff(client):
    resp = await client.post("/review", json={"diff": "", "file_path": "test.py"})
    assert resp.status_code == 422


async def test_review_validation_missing_file_path(client):
    resp = await client.post("/review", json={"diff": "+hello"})
    assert resp.status_code == 422


MOCK_AI_RESPONSE = json.dumps({
    "summary": "Looks good overall.",
    "findings": [
        {
            "file": "test.py",
            "line": 5,
            "severity": "medium",
            "title": "Unused variable",
            "description": "Variable x is assigned but never used.",
            "suggestion": "Remove the unused variable.",
            "confidence": 0.85,
        }
    ],
})


@patch("app.services.ai_reviewer.AsyncOpenAI")
async def test_review_success(mock_openai_cls, client):
    mock_client = AsyncMock()
    mock_openai_cls.return_value = mock_client

    mock_choice = AsyncMock()
    mock_choice.message.content = MOCK_AI_RESPONSE
    mock_response = AsyncMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response

    resp = await client.post("/review", json={
        "diff": "+x = 1\n+y = 2",
        "file_path": "test.py",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data
    assert len(data["findings"]) == 1
    assert data["findings"][0]["severity"] == "medium"


async def test_review_no_api_key(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    # Need to reload settings
    from app.core.config import Settings
    with patch("app.api.routes.settings", Settings(openai_api_key="")):
        resp = await client.post("/review", json={
            "diff": "+hello",
            "file_path": "test.py",
        })
        assert resp.status_code == 503
