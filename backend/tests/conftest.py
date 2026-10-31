import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from tests.constants import TEST_WEBHOOK_SECRET


@pytest.fixture
def client():
    """A test client whose settings use a known secret and never read the real `.env`."""
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, github_webhook_secret=TEST_WEBHOOK_SECRET
    )
    yield TestClient(app)
    app.dependency_overrides.clear()
