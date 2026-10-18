from pydantic import BaseModel, Field


class ReviewRequest(BaseModel):
    """Input for the /review endpoint."""

    diff: str = Field(..., min_length=1, max_length=200_000, description="Unified diff text")
    file_path: str = Field(..., min_length=1, max_length=500, description="File path in repo")
    language: str = Field(default="", max_length=50, description="Programming language hint")


class ReviewFinding(BaseModel):
    file: str
    line: int | None = None
    severity: str = Field(..., pattern=r"^(critical|high|medium|low)$")
    title: str
    description: str
    suggestion: str = ""
    confidence: float = Field(..., ge=0.0, le=1.0)


class ReviewResponse(BaseModel):
    summary: str
    findings: list[ReviewFinding] = []
    model: str = ""
    files_reviewed: int = 0


class PRReviewRequest(BaseModel):
    """Input for reviewing an entire PR via the API."""

    owner: str = Field(..., min_length=1, max_length=100)
    repo: str = Field(..., min_length=1, max_length=100)
    pr_number: int = Field(..., gt=0)
    github_token: str | None = Field(default=None, description="Override token for this request")
