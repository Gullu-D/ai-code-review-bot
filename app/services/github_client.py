"""GitHub API client for PR metadata, diffs, and review publishing."""

from __future__ import annotations

import hashlib
import hmac

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.review import ReviewFinding
from app.services.diff_parser import FileDiff

logger = get_logger(__name__)

BASE_URL = "https://api.github.com"
BOT_TAG = "<!-- ai-code-review-bot -->"


class GitHubClient:
    def __init__(self, token: str | None = None):
        self.token = token or settings.github_token
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=BASE_URL,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def get_pr(self, owner: str, repo: str, pr_number: int) -> dict:
        client = await self._get_client()
        resp = await client.get(f"/repos/{owner}/{repo}/pulls/{pr_number}")
        resp.raise_for_status()
        return resp.json()

    async def get_pr_files(self, owner: str, repo: str, pr_number: int) -> list[dict]:
        """Fetch all changed files with pagination."""
        client = await self._get_client()
        files: list[dict] = []
        page = 1
        while True:
            resp = await client.get(
                f"/repos/{owner}/{repo}/pulls/{pr_number}/files",
                params={"per_page": 100, "page": page},
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            files.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return files

    async def get_existing_reviews(self, owner: str, repo: str, pr_number: int) -> list[dict]:
        """Fetch existing reviews to detect duplicates."""
        client = await self._get_client()
        resp = await client.get(f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews")
        resp.raise_for_status()
        return resp.json()

    async def post_review(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        commit_sha: str,
        summary: str,
        findings: list[ReviewFinding],
        file_diffs: list[FileDiff],
    ) -> dict | None:
        # Check for duplicate bot review on same commit
        existing = await self.get_existing_reviews(owner, repo, pr_number)
        short_sha = commit_sha[:8]
        for review in existing:
            body = review.get("body") or ""
            if BOT_TAG in body and short_sha in body:
                logger.info("Skipping duplicate review for commit %s", short_sha)
                return None

        # Build position lookup: {file_path: {line: position}}
        position_map: dict[str, dict[int, int]] = {}
        for fd in file_diffs:
            position_map[fd.path] = fd.added_lines

        comments = []
        for finding in findings[: settings.review_max_comments]:
            if not finding.line or finding.file not in position_map:
                continue
            pos = position_map[finding.file].get(finding.line)
            if pos is None:
                continue
            sev = finding.severity.upper()
            body = (
                f"**{sev}** ({finding.confidence:.0%} confidence): "
                f"{finding.title}\n\n{finding.description}"
            )
            if finding.suggestion:
                body += f"\n\n**Suggestion:** {finding.suggestion}"
            comments.append({"path": finding.file, "position": pos, "body": body})

        body = f"{BOT_TAG}\n\n**AI Code Review** (commit: `{commit_sha[:8]}`)\n\n{summary}"
        if not findings:
            body += "\n\n:white_check_mark: No issues found."

        event = "COMMENT"
        payload: dict = {
            "commit_id": commit_sha,
            "body": body,
            "event": event,
        }
        if comments:
            payload["comments"] = comments

        client = await self._get_client()
        resp = await client.post(
            f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            json=payload,
        )
        resp.raise_for_status()
        logger.info(
            "Posted review with %d inline comments on %s/%s#%d",
            len(comments), owner, repo, pr_number,
        )
        return resp.json()


def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub HMAC-SHA256 webhook signature."""
    if not signature.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)
