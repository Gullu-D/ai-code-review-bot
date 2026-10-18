import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.review import ReviewFinding
from app.services.diff_parser import FileDiff
from app.services.github_client import GitHubClient, verify_webhook_signature


def test_webhook_signature_valid():
    secret = "mysecret"
    payload = b'{"action":"opened"}'
    sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert verify_webhook_signature(payload, sig, secret) is True


def test_webhook_signature_invalid():
    assert verify_webhook_signature(b"data", "sha256=wrong", "secret") is False


def test_webhook_signature_bad_prefix():
    assert verify_webhook_signature(b"data", "sha1=abc", "secret") is False


@pytest.fixture
def mock_httpx_response():
    """Helper to build mock httpx responses."""
    def _make(json_data, status=200):
        resp = MagicMock()
        resp.json.return_value = json_data
        resp.status_code = status
        resp.raise_for_status = MagicMock()
        return resp
    return _make


async def test_get_pr_files_pagination(mock_httpx_response):
    gh = GitHubClient(token="fake-token")
    client_mock = AsyncMock()
    # Page 1: 100 items, page 2: 5 items
    page1 = [{"filename": f"f{i}.py", "patch": "+x", "status": "modified"} for i in range(100)]
    page2 = [{"filename": f"g{i}.py", "patch": "+y", "status": "modified"} for i in range(5)]
    client_mock.get.side_effect = [
        mock_httpx_response(page1),
        mock_httpx_response(page2),
    ]
    gh._client = client_mock
    files = await gh.get_pr_files("owner", "repo", 1)
    assert len(files) == 105
    await gh.close()


async def test_post_review_skips_duplicate(mock_httpx_response):
    gh = GitHubClient(token="fake-token")
    client_mock = AsyncMock()
    # Use a realistic 40-char SHA — the body only stores the first 8 chars
    full_sha = "abc12345deadbeef1234567890abcdef12345678"
    existing_review = {
        "body": f"<!-- ai-code-review-bot -->\n\n**AI Code Review** (commit: `{full_sha[:8]}`)",
    }
    client_mock.get.return_value = mock_httpx_response([existing_review])
    gh._client = client_mock

    result = await gh.post_review("o", "r", 1, full_sha, "summary", [], [])
    assert result is None
    client_mock.post.assert_not_called()
    await gh.close()


async def test_post_review_not_duplicate_different_commit(mock_httpx_response):
    gh = GitHubClient(token="fake-token")
    client_mock = AsyncMock()
    existing_review = {
        "body": "<!-- ai-code-review-bot -->\n\n**AI Code Review** (commit: `old12345`)",
    }
    client_mock.get.return_value = mock_httpx_response([existing_review])
    client_mock.post.return_value = mock_httpx_response({"id": 789})
    gh._client = client_mock

    result = await gh.post_review("o", "r", 1, "new12345" + "0" * 32, "summary", [], [])
    assert result is not None
    client_mock.post.assert_called_once()
    await gh.close()


async def test_post_review_with_findings(mock_httpx_response):
    gh = GitHubClient(token="fake-token")
    client_mock = AsyncMock()
    # No existing reviews
    client_mock.get.return_value = mock_httpx_response([])
    client_mock.post.return_value = mock_httpx_response({"id": 123})
    gh._client = client_mock

    finding = ReviewFinding(
        file="app.py", line=2, severity="high",
        title="Bug", description="Bad thing", suggestion="Fix it", confidence=0.9,
    )
    diff = FileDiff(
        path="app.py", patch="@@ -1,2 +1,3 @@\n ctx\n+new_line\n ctx",
        added_lines={2: 3},
    )

    result = await gh.post_review("o", "r", 1, "abc123", "summary", [finding], [diff])
    assert result is not None
    client_mock.post.assert_called_once()
    call_json = client_mock.post.call_args.kwargs["json"]
    assert len(call_json["comments"]) == 1
    assert call_json["comments"][0]["position"] == 3
    await gh.close()


async def test_post_review_skips_unmatched_finding(mock_httpx_response):
    gh = GitHubClient(token="fake-token")
    client_mock = AsyncMock()
    client_mock.get.return_value = mock_httpx_response([])
    client_mock.post.return_value = mock_httpx_response({"id": 456})
    gh._client = client_mock

    # Finding on line 99 which isn't in the diff
    finding = ReviewFinding(
        file="app.py", line=99, severity="low",
        title="Style", description="Meh", confidence=0.5,
    )
    diff = FileDiff(path="app.py", patch="@@ -1,2 +1,3 @@\n ctx\n+new\n ctx", added_lines={2: 3})

    await gh.post_review("o", "r", 1, "abc", "ok", [finding], [diff])
    call_json = client_mock.post.call_args.kwargs["json"]
    assert "comments" not in call_json  # unmatched findings produce no inline comments
    await gh.close()
