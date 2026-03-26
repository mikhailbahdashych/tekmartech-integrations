"""Parse credential_envelope and extract per-type credential fields.

Each MCP server type receives credentials in a specific structure defined
in mcp-tool-interface.yaml under credential_structures. This module validates
the envelope and extracts the typed credentials.

IMPORTANT: This module NEVER logs credential values. Only credential_mode
and server_type may appear in logs.
"""

from __future__ import annotations

import json

import structlog

from shared.models import (
    AWSCredentials,
    CredentialEnvelope,
    GitHubCredentials,
    GoogleWorkspaceCredentials,
)

logger = structlog.get_logger()


def extract_github_credentials(envelope: CredentialEnvelope) -> GitHubCredentials:
    """Parse and validate GitHub credentials from a credential envelope.

    Validates that the server_type is 'github' and that credential_data
    contains the required fields (personal_access_token, organization).

    Args:
        envelope: The credential envelope from the tool invocation request.

    Returns:
        A validated GitHubCredentials instance.

    Raises:
        ValueError: If server_type does not match 'github'.
        pydantic.ValidationError: If required credential fields are missing.
    """
    if envelope.server_type != "github":
        logger.error(
            "credential_type_mismatch",
            module="shared",
            action="extract_credentials",
            expected="github",
            received=envelope.server_type,
        )
        raise ValueError(f"Expected server_type 'github', got '{envelope.server_type}'.")

    logger.debug(
        "extracting_github_credentials",
        module="shared",
        action="extract_credentials",
        credential_mode=envelope.credential_mode,
    )

    return GitHubCredentials.model_validate(envelope.credential_data)


def extract_aws_credentials(envelope: CredentialEnvelope) -> AWSCredentials:
    """Parse and validate AWS credentials from a credential envelope.

    Validates that the server_type is 'aws' and that credential_data
    contains the required fields (access_key_id, secret_access_key, region).
    session_token is optional (present in broker mode).

    Args:
        envelope: The credential envelope from the tool invocation request.

    Returns:
        A validated AWSCredentials instance.

    Raises:
        ValueError: If server_type does not match 'aws'.
        pydantic.ValidationError: If required credential fields are missing.
    """
    if envelope.server_type != "aws":
        logger.error(
            "credential_type_mismatch",
            module="shared",
            action="extract_credentials",
            expected="aws",
            received=envelope.server_type,
        )
        raise ValueError(f"Expected server_type 'aws', got '{envelope.server_type}'.")

    logger.debug(
        "extracting_aws_credentials",
        module="shared",
        action="extract_credentials",
        credential_mode=envelope.credential_mode,
    )

    return AWSCredentials.model_validate(envelope.credential_data)


_REQUIRED_SA_FIELDS = {"type", "project_id", "private_key_id", "private_key", "client_email"}


def extract_google_workspace_credentials(
    envelope: CredentialEnvelope,
) -> GoogleWorkspaceCredentials:
    """Parse and validate Google Workspace credentials from a credential envelope.

    Validates that the server_type is 'google_workspace', parses the
    service_account_json string into a dict, and checks that required
    service account key fields are present.

    Args:
        envelope: The credential envelope from the tool invocation request.

    Returns:
        A validated GoogleWorkspaceCredentials instance.

    Raises:
        ValueError: If server_type mismatch, JSON parsing fails, or required fields missing.
        pydantic.ValidationError: If required credential fields are missing.
    """
    if envelope.server_type != "google_workspace":
        logger.error(
            "credential_type_mismatch",
            module="shared",
            action="extract_credentials",
            expected="google_workspace",
            received=envelope.server_type,
        )
        raise ValueError(f"Expected server_type 'google_workspace', got '{envelope.server_type}'.")

    logger.debug(
        "extracting_google_workspace_credentials",
        module="shared",
        action="extract_credentials",
        credential_mode=envelope.credential_mode,
    )

    creds = GoogleWorkspaceCredentials.model_validate(envelope.credential_data)

    # Validate the service_account_json is parseable and has required fields
    try:
        sa_info = json.loads(creds.service_account_json)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"service_account_json is not valid JSON: {exc}") from exc

    missing = _REQUIRED_SA_FIELDS - set(sa_info.keys())
    if missing:
        raise ValueError(
            f"service_account_json missing required fields: {', '.join(sorted(missing))}"
        )

    return creds
