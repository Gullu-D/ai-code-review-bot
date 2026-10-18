import pytest


@pytest.fixture(autouse=True)
def _mock_env(monkeypatch):
    """Ensure tests never use real credentials."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key-for-testing")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_fake_token")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "test-webhook-secret")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
