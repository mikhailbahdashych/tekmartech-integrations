"""Tests for shared.credential_handler."""

import pytest
from pydantic import ValidationError

from shared.credential_handler import extract_github_credentials
from shared.models import CredentialEnvelope


def _github_envelope(**overrides):
    """Build a GitHub credential envelope with optional overrides."""
    base = {
        "server_type": "github",
        "credential_mode": "direct",
        "credential_data": {
            "personal_access_token": "ghp_test1234567890abcdef1234567890abcdef",
            "organization": "test-org",
        },
    }
    base.update(overrides)
    return CredentialEnvelope.model_validate(base)


def test_extract_github_credentials_valid():
    envelope = _github_envelope()
    creds = extract_github_credentials(envelope)
    assert creds.personal_access_token == "ghp_test1234567890abcdef1234567890abcdef"  # noqa: S105
    assert creds.organization == "test-org"


def test_extract_github_credentials_wrong_server_type():
    envelope = _github_envelope(server_type="aws")
    with pytest.raises(ValueError, match="Expected server_type 'github', got 'aws'"):
        extract_github_credentials(envelope)


def test_extract_github_credentials_missing_pat():
    envelope = _github_envelope(credential_data={"organization": "test-org"})
    with pytest.raises(ValidationError):
        extract_github_credentials(envelope)


def test_extract_github_credentials_missing_organization():
    envelope = _github_envelope(
        credential_data={"personal_access_token": "ghp_test1234567890abcdef1234567890abcdef"}
    )
    with pytest.raises(ValidationError):
        extract_github_credentials(envelope)


def test_extract_github_credentials_broker_mode():
    envelope = _github_envelope(credential_mode="broker")
    creds = extract_github_credentials(envelope)
    assert creds.organization == "test-org"
