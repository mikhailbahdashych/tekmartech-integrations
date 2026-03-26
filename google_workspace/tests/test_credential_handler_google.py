"""Tests for Google Workspace credential extraction in shared.credential_handler."""

import json

import pytest

from google_workspace.tests.conftest import MOCK_DELEGATED_EMAIL, MOCK_SERVICE_ACCOUNT_JSON
from shared.credential_handler import extract_google_workspace_credentials
from shared.models import CredentialEnvelope


def test_extract_google_credentials_valid():
    envelope = CredentialEnvelope(
        server_type="google_workspace",
        credential_mode="direct",
        credential_data={
            "service_account_json": MOCK_SERVICE_ACCOUNT_JSON,
            "delegated_email": MOCK_DELEGATED_EMAIL,
        },
    )
    creds = extract_google_workspace_credentials(envelope)
    assert creds.delegated_email == MOCK_DELEGATED_EMAIL
    # Verify the JSON is parseable
    sa_info = json.loads(creds.service_account_json)
    assert sa_info["type"] == "service_account"


def test_extract_google_credentials_without_delegated_email():
    envelope = CredentialEnvelope(
        server_type="google_workspace",
        credential_mode="direct",
        credential_data={
            "service_account_json": MOCK_SERVICE_ACCOUNT_JSON,
        },
    )
    creds = extract_google_workspace_credentials(envelope)
    assert creds.delegated_email is None


def test_extract_google_credentials_wrong_server_type():
    envelope = CredentialEnvelope(
        server_type="aws",
        credential_mode="direct",
        credential_data={
            "service_account_json": MOCK_SERVICE_ACCOUNT_JSON,
        },
    )
    with pytest.raises(ValueError, match="Expected server_type 'google_workspace'"):
        extract_google_workspace_credentials(envelope)


def test_extract_google_credentials_invalid_json():
    envelope = CredentialEnvelope(
        server_type="google_workspace",
        credential_mode="direct",
        credential_data={
            "service_account_json": "not-valid-json{{{",
        },
    )
    with pytest.raises(ValueError, match="not valid JSON"):
        extract_google_workspace_credentials(envelope)


def test_extract_google_credentials_missing_required_fields():
    incomplete_sa = json.dumps({"type": "service_account", "project_id": "test"})
    envelope = CredentialEnvelope(
        server_type="google_workspace",
        credential_mode="direct",
        credential_data={
            "service_account_json": incomplete_sa,
        },
    )
    with pytest.raises(ValueError, match="missing required fields"):
        extract_google_workspace_credentials(envelope)


def test_extract_google_credentials_missing_sa_json():
    envelope = CredentialEnvelope(
        server_type="google_workspace",
        credential_mode="direct",
        credential_data={
            "delegated_email": "admin@example.com",
        },
    )
    with pytest.raises(Exception):  # noqa: B017
        extract_google_workspace_credentials(envelope)
