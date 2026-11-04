import pytest
from pydantic import ValidationError

from app.config import Settings
from tests.constants import TEST_APP_ID

VALID_SECRET = "x" * 32
ENV_KEYS = (
    "ENVIRONMENT",
    "AI_PROVIDER",
    "GITHUB_WEBHOOK_SECRET",
    "GITHUB_APP_ID",
    "GITHUB_PRIVATE_KEY_PATH",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Isolate every test from the real shell environment."""
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def required(private_key_file) -> dict:
    """The minimum valid values for every required setting."""
    return {
        "github_webhook_secret": VALID_SECRET,
        "github_app_id": TEST_APP_ID,
        "github_private_key_path": private_key_file,
    }


@pytest.fixture
def make_settings(required):
    def make(**overrides) -> Settings:
        # _env_file=None: never read the developer's real .env in tests
        return Settings(_env_file=None, **{**required, **overrides})

    return make


def test_defaults(make_settings):
    settings = make_settings()

    assert settings.environment == "development"
    assert settings.ai_provider == "none"


def test_reads_environment_variables(monkeypatch, private_key_file):
    monkeypatch.setenv("AI_PROVIDER", "github")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", VALID_SECRET)
    monkeypatch.setenv("GITHUB_APP_ID", "5595663")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY_PATH", str(private_key_file))

    settings = Settings(_env_file=None)

    assert settings.ai_provider == "github"
    assert settings.github_webhook_secret.get_secret_value() == VALID_SECRET
    assert settings.github_app_id == 5595663
    assert settings.github_private_key_path == private_key_file


@pytest.mark.parametrize("provider", ["none", "fake", "github"])
def test_accepts_every_valid_ai_provider(make_settings, provider):
    assert make_settings(ai_provider=provider).ai_provider == provider


@pytest.mark.parametrize("provider", ["openai", "", "GITHUB "])
def test_rejects_unknown_ai_provider(make_settings, provider):
    with pytest.raises(ValidationError):
        make_settings(ai_provider=provider)


@pytest.mark.parametrize(
    "missing", ["github_webhook_secret", "github_app_id", "github_private_key_path"]
)
def test_each_required_setting_is_enforced(required, missing):
    # Leave out exactly one field, and check the error is about that field,
    # so the test can't pass just because some *other* field is missing.
    values = {k: v for k, v in required.items() if k != missing}

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, **values)

    assert [e["loc"] for e in error.value.errors()] == [(missing,)]


# Boundary values around the 32-character minimum.


def test_webhook_secret_at_minimum_length_is_accepted(make_settings):
    assert make_settings(github_webhook_secret="x" * 32)


@pytest.mark.parametrize("secret", ["", "x" * 31])
def test_webhook_secret_too_short_fails(make_settings, secret):
    with pytest.raises(ValidationError):
        make_settings(github_webhook_secret=secret)


def test_secret_is_hidden_when_printed(make_settings):
    settings = make_settings()

    assert VALID_SECRET not in repr(settings)
    assert VALID_SECRET not in str(settings.github_webhook_secret)


# App ID: must be a positive integer (boundary: 1 is the smallest valid ID).


def test_app_id_minimum_is_accepted(make_settings):
    assert make_settings(github_app_id=1).github_app_id == 1


@pytest.mark.parametrize("app_id", [0, -1, "abc"])
def test_invalid_app_id_fails(make_settings, app_id):
    with pytest.raises(ValidationError):
        make_settings(github_app_id=app_id)


# Private key path: must point to an existing file.


def test_missing_key_file_fails(make_settings, tmp_path):
    with pytest.raises(ValidationError):
        make_settings(github_private_key_path=tmp_path / "does-not-exist.pem")


def test_key_path_that_is_a_directory_fails(make_settings, tmp_path):
    with pytest.raises(ValidationError):
        make_settings(github_private_key_path=tmp_path)
