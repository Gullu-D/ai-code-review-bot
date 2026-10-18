from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    github_token: str = ""
    github_webhook_secret: str = ""

    review_max_files: int = 20
    review_max_diff_chars: int = 50_000
    review_max_comments: int = 25

    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
