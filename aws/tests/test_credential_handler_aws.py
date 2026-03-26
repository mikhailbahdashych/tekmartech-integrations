"""Tests for AWS credential extraction in shared.credential_handler."""

import pytest
from pydantic import ValidationError

from shared.credential_handler import extract_aws_credentials
from shared.models import CredentialEnvelope


def test_extract_aws_credentials_direct_mode():
    envelope = CredentialEnvelope(
        server_type="aws",
        credential_mode="direct",
        credential_data={
            "access_key_id": "AKIAIOSFODNN7EXAMPLE",
            "secret_access_key": "wJalrXUtnFEMI",
            "region": "us-east-1",
        },
    )
    creds = extract_aws_credentials(envelope)
    assert creds.access_key_id == "AKIAIOSFODNN7EXAMPLE"
    assert creds.region == "us-east-1"
    assert creds.session_token is None


def test_extract_aws_credentials_broker_mode():
    envelope = CredentialEnvelope(
        server_type="aws",
        credential_mode="broker",
        credential_data={
            "access_key_id": "ASIAIOSFODNN7EXAMPLE",
            "secret_access_key": "wJalrXUtnFEMI",
            "session_token": "FwoGZXIvYXdzEA0aDHtest",
            "region": "eu-west-1",
        },
    )
    creds = extract_aws_credentials(envelope)
    assert creds.session_token == "FwoGZXIvYXdzEA0aDHtest"  # noqa: S105
    assert creds.region == "eu-west-1"


def test_extract_aws_credentials_wrong_server_type():
    envelope = CredentialEnvelope(
        server_type="github",
        credential_mode="direct",
        credential_data={
            "access_key_id": "AKIAIOSFODNN7EXAMPLE",
            "secret_access_key": "wJalrXUtnFEMI",
            "region": "us-east-1",
        },
    )
    with pytest.raises(ValueError, match="Expected server_type 'aws', got 'github'"):
        extract_aws_credentials(envelope)


def test_extract_aws_credentials_missing_region():
    envelope = CredentialEnvelope(
        server_type="aws",
        credential_mode="direct",
        credential_data={
            "access_key_id": "AKIAIOSFODNN7EXAMPLE",
            "secret_access_key": "wJalrXUtnFEMI",
        },
    )
    with pytest.raises(ValidationError):
        extract_aws_credentials(envelope)


def test_extract_aws_credentials_missing_access_key():
    envelope = CredentialEnvelope(
        server_type="aws",
        credential_mode="direct",
        credential_data={
            "secret_access_key": "wJalrXUtnFEMI",
            "region": "us-east-1",
        },
    )
    with pytest.raises(ValidationError):
        extract_aws_credentials(envelope)
