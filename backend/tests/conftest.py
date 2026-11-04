import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from tests.constants import TEST_APP_ID, TEST_WEBHOOK_SECRET


@pytest.fixture(scope="session")
def private_key_pem() -> str:
    """A throwaway RSA key in the same format GitHub issues. Never the real app key."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()


@pytest.fixture(scope="session")
def private_key_file(tmp_path_factory, private_key_pem):
    path = tmp_path_factory.mktemp("keys") / "test-app.private-key.pem"
    path.write_text(private_key_pem)
    return path


@pytest.fixture
def test_settings(private_key_file) -> Settings:
    """Settings with known test values that never read the real `.env`."""
    return Settings(
        _env_file=None,
        github_webhook_secret=TEST_WEBHOOK_SECRET,
        github_app_id=TEST_APP_ID,
        github_private_key_path=private_key_file,
    )


@pytest.fixture
def client(test_settings):
    app.dependency_overrides[get_settings] = lambda: test_settings
    yield TestClient(app)
    app.dependency_overrides.clear()
