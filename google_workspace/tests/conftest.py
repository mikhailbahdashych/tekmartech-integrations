"""Shared fixtures for Google Workspace MCP server tests."""

import json

import pytest

import google_workspace.client as gw_client_mod
from shared.models import CredentialEnvelope

# A minimal but valid-looking service account JSON for testing.
# This is NOT a real key — it's a structural template for mock validation.
MOCK_SERVICE_ACCOUNT_JSON = json.dumps(
    {
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "key123",
        "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIBogIBAAJBALRm"
        "OpHI0EXAMPLE_FAKE_KEY_NOT_REAL\n-----END RSA PRIVATE KEY-----\n",
        "client_email": "test@test-project.iam.gserviceaccount.com",
        "client_id": "123456789",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
)

MOCK_DELEGATED_EMAIL = "admin@example.com"


@pytest.fixture(autouse=True)
def _gw_test_env(monkeypatch):
    """Disable asyncio.to_thread for Google API calls in tests."""
    monkeypatch.setattr(gw_client_mod, "_use_thread", False)


@pytest.fixture
def gw_credentials() -> CredentialEnvelope:
    """A valid Google Workspace credential envelope for testing."""
    return CredentialEnvelope(
        server_type="google_workspace",
        credential_mode="direct",
        credential_data={
            "service_account_json": MOCK_SERVICE_ACCOUNT_JSON,
            "delegated_email": MOCK_DELEGATED_EMAIL,
        },
    )


@pytest.fixture
def invocation_id() -> str:
    """A fixed UUID for test invocations."""
    return "gw-test-550e8400-e29b-41d4-a716-446655440000"
