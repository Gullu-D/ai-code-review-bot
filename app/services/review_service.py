"""Orchestrates PR review: fetch files, run AI review, post results."""

from __future__ import annotations

from app.core.logging import get_logger
from app.schemas.review import ReviewResponse
from app.services.ai_reviewer import review_multiple_diffs
from app.services.diff_parser import parse_pr_files
from app.services.github_client import GitHubClient

logger = get_logger(__name__)


async def review_pull_request(
    owner: str,
    repo: str,
    pr_number: int,
    github_token: str | None = None,
    post_review: bool = True,
) -> ReviewResponse:
    gh = GitHubClient(token=github_token)
    try:
        pr = await gh.get_pr(owner, repo, pr_number)
        commit_sha = pr["head"]["sha"]

        raw_files = await gh.get_pr_files(owner, repo, pr_number)
        file_diffs = parse_pr_files(raw_files)

        if not file_diffs:
            return ReviewResponse(summary="No reviewable file changes.", files_reviewed=0)

        # Prepare for AI review
        review_files = [{"path": fd.path, "patch": fd.patch} for fd in file_diffs]
        result = await review_multiple_diffs(review_files, api_key=None)
        result.files_reviewed = len(file_diffs)

        if post_review:
            await gh.post_review(
                owner, repo, pr_number, commit_sha,
                result.summary, result.findings, file_diffs,
            )

        return result
    finally:
        await gh.close()
