import pytest
from pydantic import ValidationError

from app.config import Settings

VALID_SECRET = "x" * 32


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Isolate every test from the real shell environment."""
    for key in ("ENVIRONMENT", "AI_PROVIDER", "GITHUB_WEBHOOK_SECRET"):
        monkeypatch.delenv(key, raising=False)


def make_settings(**overrides) -> Settings:
    # _env_file=None: never read the developer's real .env in tests
    return Settings(_env_file=None, **{"github_webhook_secret": VALID_SECRET, **overrides})


def test_defaults():
    settings = make_settings()

    assert settings.environment == "development"
    assert settings.ai_provider == "none"


def test_reads_environment_variables(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "github")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", VALID_SECRET)

    settings = Settings(_env_file=None)

    assert settings.ai_provider == "github"
    assert settings.github_webhook_secret.get_secret_value() == VALID_SECRET


@pytest.mark.parametrize("provider", ["none", "fake", "github"])
def test_accepts_every_valid_ai_provider(provider):
    assert make_settings(ai_provider=provider).ai_provider == provider


@pytest.mark.parametrize("provider", ["openai", "", "GITHUB "])
def test_rejects_unknown_ai_provider(provider):
    with pytest.raises(ValidationError):
        make_settings(ai_provider=provider)


def test_missing_webhook_secret_fails():
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


# Boundary values around the 32-character minimum.


def test_webhook_secret_at_minimum_length_is_accepted():
    assert make_settings(github_webhook_secret="x" * 32)


@pytest.mark.parametrize("secret", ["", "x" * 31])
def test_webhook_secret_too_short_fails(secret):
    with pytest.raises(ValidationError):
        make_settings(github_webhook_secret=secret)


def test_secret_is_hidden_when_printed():
    settings = make_settings()

    assert VALID_SECRET not in repr(settings)
    assert VALID_SECRET not in str(settings.github_webhook_secret)
