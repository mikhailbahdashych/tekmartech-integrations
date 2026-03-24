"""Parse credential_envelope and extract per-type credential fields.

Each MCP server type receives credentials in a specific structure defined
in mcp-tool-interface.yaml under credential_structures. This module validates
the envelope and extracts the typed credentials.

IMPORTANT: This module NEVER logs credential values. Only credential_mode
and server_type may appear in logs.
"""

from __future__ import annotations

import structlog

from shared.models import CredentialEnvelope, GitHubCredentials

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
