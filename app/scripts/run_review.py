"""Script for GitHub Actions: review the current PR and post results."""

import asyncio
import json
import os
import sys


async def main() -> None:
    # These are provided by GitHub Actions environment
    github_token = os.environ.get("GITHUB_TOKEN", "")
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")

    if not github_token:
        print("ERROR: GITHUB_TOKEN not set")
        sys.exit(1)

    if not event_path or not os.path.exists(event_path):
        print("ERROR: GITHUB_EVENT_PATH not set or missing")
        sys.exit(1)

    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if not openai_key:
        print("ERROR: OPENAI_API_KEY not set")
        sys.exit(1)

    with open(event_path) as f:
        event = json.load(f)

    pr = event.get("pull_request", {})
    repo = event.get("repository", {})
    owner = repo.get("owner", {}).get("login", "")
    repo_name = repo.get("name", "")
    pr_number = pr.get("number", 0)

    if not all([owner, repo_name, pr_number]):
        print("ERROR: Could not extract PR info from event payload")
        sys.exit(1)

    print(f"Reviewing {owner}/{repo_name}#{pr_number}...")

    # Import here so env vars are loaded first
    from app.services.review_service import review_pull_request

    result = await review_pull_request(
        owner, repo_name, pr_number,
        github_token=github_token,
        post_review=True,
    )

    print(f"Review complete: {len(result.findings)} findings across {result.files_reviewed} files")
    print(f"Summary: {result.summary}")

    # Exit non-zero only on critical findings (optional strictness)
    critical = [f for f in result.findings if f.severity == "critical"]
    if critical:
        print(f"WARNING: {len(critical)} critical finding(s) detected")


if __name__ == "__main__":
    asyncio.run(main())
