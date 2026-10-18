import json
from unittest.mock import AsyncMock, patch

from app.services.ai_reviewer import _parse_response, review_diff, review_multiple_diffs


def test_parse_valid_response():
    raw = json.dumps({
        "summary": "All good.",
        "findings": [
            {
                "file": "main.py",
                "line": 10,
                "severity": "high",
                "title": "SQL injection",
                "description": "User input passed directly to query.",
                "suggestion": "Use parameterized queries.",
                "confidence": 0.95,
            }
        ],
    })
    result = _parse_response(raw, "gpt-4o-mini")
    assert result.summary == "All good."
    assert len(result.findings) == 1
    assert result.findings[0].severity == "high"


def test_parse_empty_findings():
    raw = json.dumps({"summary": "Clean code.", "findings": []})
    result = _parse_response(raw, "gpt-4o-mini")
    assert result.findings == []


def test_parse_malformed_json():
    result = _parse_response("not json at all", "gpt-4o-mini")
    assert "malformed" in result.summary.lower()
    assert result.findings == []


def test_parse_malformed_finding_skipped():
    raw = json.dumps({
        "summary": "Issues found.",
        "findings": [
            {"severity": "invalid-severity", "confidence": 2.0},
            {
                "file": "a.py", "line": 1, "severity": "low",
                "title": "ok", "description": "ok", "confidence": 0.5,
            },
        ],
    })
    result = _parse_response(raw, "gpt-4o-mini")
    assert len(result.findings) == 1


@patch("app.services.ai_reviewer.AsyncOpenAI")
async def test_review_diff_rate_limit(mock_cls):
    from openai import RateLimitError
    mock_client = AsyncMock()
    mock_cls.return_value = mock_client
    mock_client.chat.completions.create.side_effect = RateLimitError(
        message="rate limit",
        response=AsyncMock(status_code=429, headers={}),
        body=None,
    )
    result = await review_diff("+code", "test.py")
    assert "rate limit" in result.summary.lower()


@patch("app.services.ai_reviewer.AsyncOpenAI")
async def test_review_diff_timeout(mock_cls):
    from openai import APITimeoutError
    mock_client = AsyncMock()
    mock_cls.return_value = mock_client
    mock_client.chat.completions.create.side_effect = APITimeoutError(request=AsyncMock())
    result = await review_diff("+code", "test.py")
    assert "timed out" in result.summary.lower()


@patch("app.services.ai_reviewer.AsyncOpenAI")
async def test_review_multiple_empty(mock_cls):
    result = await review_multiple_diffs([])
    assert result.files_reviewed == 0
