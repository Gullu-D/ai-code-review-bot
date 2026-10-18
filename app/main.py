"""FastAPI application entry point."""

from fastapi import FastAPI

from app.api.routes import router
from app.core.logging import setup_logging

setup_logging()

app = FastAPI(
    title="AI Code Review Bot",
    version="0.1.0",
    description="Automated AI-powered code review for GitHub pull requests",
)

app.include_router(router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
