"""FastAPI route handlers."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.review import PRReviewRequest, ReviewRequest, ReviewResponse
from app.services.ai_reviewer import review_diff
from app.services.github_client import verify_webhook_signature
from app.services.review_service import review_pull_request

logger = get_logger(__name__)

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "healthy", "model": settings.openai_model}


@router.get("/")
async def root() -> dict:
    return {
        "service": "AI Code Review Bot",
        "version": "0.1.0",
        "endpoints": ["/health", "/review", "/review/pr", "/webhook/github"],
    }


@router.post("/review", response_model=ReviewResponse)
async def review_code(req: ReviewRequest) -> ReviewResponse:
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OpenAI API key not configured")

    if len(req.diff) > settings.review_max_diff_chars:
        raise HTTPException(
            status_code=413,
            detail=f"Diff exceeds max size ({settings.review_max_diff_chars} chars)",
        )

    return await review_diff(req.diff, req.file_path, req.language)


@router.post("/review/pr", response_model=ReviewResponse)
async def review_pr(req: PRReviewRequest) -> ReviewResponse:
    token = req.github_token or settings.github_token
    if not token:
        raise HTTPException(status_code=503, detail="GitHub token not configured")
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OpenAI API key not configured")

    try:
        return await review_pull_request(
            req.owner, req.repo, req.pr_number,
            github_token=token, post_review=True,
        )
    except Exception as e:
        logger.error("PR review failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str = Header(default=""),
    x_github_event: str = Header(default=""),
) -> dict:
    body = await request.body()

    # Verify signature
    secret = settings.github_webhook_secret
    if not secret:
        raise HTTPException(status_code=503, detail="Webhook secret not configured")
    if not verify_webhook_signature(body, x_hub_signature_256, secret):
        raise HTTPException(status_code=401, detail="Invalid signature")

    if x_github_event != "pull_request":
        return {"status": "ignored", "event": x_github_event}

    payload = await request.json()
    action = payload.get("action", "")
    if action not in ("opened", "synchronize", "reopened"):
        return {"status": "ignored", "action": action}

    pr = payload.get("pull_request", {})
    repo = payload.get("repository", {})
    owner = repo.get("owner", {}).get("login", "")
    repo_name = repo.get("name", "")
    pr_number = pr.get("number", 0)

    if not all([owner, repo_name, pr_number]):
        raise HTTPException(status_code=400, detail="Missing PR metadata in payload")

    logger.info("Webhook: reviewing %s/%s#%d (%s)", owner, repo_name, pr_number, action)

    try:
        result = await review_pull_request(owner, repo_name, pr_number, post_review=True)
        return {
            "status": "reviewed",
            "pr": f"{owner}/{repo_name}#{pr_number}",
            "findings": len(result.findings),
        }
    except Exception as e:
        logger.error("Webhook review failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e)) from e
