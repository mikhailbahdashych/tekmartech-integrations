"""Shared fixtures for AWS MCP server tests."""

import pytest

import aws.client as aws_client_mod
from shared.models import CredentialEnvelope

MOCK_REGION = "us-east-1"


@pytest.fixture(autouse=True)
def _aws_env(monkeypatch):
    """Set AWS env vars so moto doesn't complain about missing credentials."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", MOCK_REGION)

    # Disable asyncio.to_thread in run_boto3 — moto mocks are thread-local.
    monkeypatch.setattr(aws_client_mod, "_use_thread", False)


@pytest.fixture
def aws_credentials() -> CredentialEnvelope:
    """A valid AWS credential envelope for testing."""
    return CredentialEnvelope(
        server_type="aws",
        credential_mode="direct",
        credential_data={
            "access_key_id": "AKIAIOSFODNN7EXAMPLE",
            "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "region": MOCK_REGION,
        },
    )


@pytest.fixture
def aws_credentials_broker() -> CredentialEnvelope:
    """AWS credentials with session token (broker mode)."""
    return CredentialEnvelope(
        server_type="aws",
        credential_mode="broker",
        credential_data={
            "access_key_id": "ASIAIOSFODNN7EXAMPLE",
            "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "session_token": "FwoGZXIvYXdzEA0aDHtest",
            "region": MOCK_REGION,
        },
    )


@pytest.fixture
def invocation_id() -> str:
    """A fixed UUID for test invocations."""
    return "aws-test-550e8400-e29b-41d4-a716-446655440000"
