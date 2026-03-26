"""Implements google_workspace.list_user_tokens from mcp-tool-interface.yaml.

Lists OAuth tokens and application-specific passwords granted by a user.
Used for access review of third-party application permissions. This API
is not paginated — Google returns all tokens in one call.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from googleapiclient.errors import HttpError

from google_workspace.client import (
    GoogleWorkspaceClient,
    handle_google_error,
    run_google_api,
)
from shared.credential_handler import extract_google_workspace_credentials
from shared.error_formatting import format_validation_error
from shared.models import CredentialEnvelope, ToolInvocationResponse
from shared.response_builder import build_error_response, build_success_response

logger = structlog.get_logger()

definition: dict[str, Any] = {
    "tool_name": "google_workspace.list_user_tokens",
    "display_name": "List User OAuth Tokens",
    "description": (
        "List OAuth tokens and application-specific passwords granted by a user. "
        "Used for access review of third-party application permissions."
    ),
    "category": "access_management",
    "input_schema": {
        "type": "object",
        "properties": {
            "user_key": {
                "type": "string",
                "description": "The user's email address.",
            },
        },
        "required": ["user_key"],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "tokens": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "client_id": {"type": "string"},
                        "display_text": {"type": "string"},
                        "scopes": {"type": "array", "items": {"type": "string"}},
                        "native_app": {"type": "boolean"},
                        "anonymous": {"type": "boolean"},
                    },
                },
            },
            "total_count": {"type": "integer"},
        },
    },
}


async def execute(
    parameters: dict[str, Any],
    credentials: CredentialEnvelope,
    invocation_id: str,
    timeout_seconds: int = 30,
) -> ToolInvocationResponse:
    """Execute the google_workspace.list_user_tokens tool.

    Args:
        parameters: Tool input (user_key).
        credentials: Credential envelope with Google service account.
        invocation_id: Unique identifier for this invocation.
        timeout_seconds: Maximum execution time.

    Returns:
        A ToolInvocationResponse with token data or error.
    """
    started_at = datetime.now(UTC)

    logger.debug(
        "tool_invocation_start",
        module="google_workspace",
        action="list_user_tokens",
        tool_name="google_workspace.list_user_tokens",
    )

    user_key = parameters.get("user_key")
    if not user_key or not isinstance(user_key, str):
        return build_error_response(
            invocation_id=invocation_id,
            error=format_validation_error("'user_key' is required and must be a non-empty string."),
            started_at=started_at,
        )

    gw_creds = extract_google_workspace_credentials(credentials)
    client = GoogleWorkspaceClient(gw_creds)
    directory = client.directory_service()

    try:
        request = directory.tokens().list(userKey=user_key)
        response = await run_google_api(client, request.execute)
    except HttpError as exc:
        return build_error_response(
            invocation_id=invocation_id,
            error=handle_google_error(exc),
            started_at=started_at,
            external_api_calls=client.api_calls,
        )

    tokens = [
        {
            "client_id": t.get("clientId", ""),
            "display_text": t.get("displayText", ""),
            "scopes": t.get("scopes", []),
            "native_app": t.get("nativeApp", False),
            "anonymous": t.get("anonymous", False),
        }
        for t in response.get("items", [])
    ]

    data = {"tokens": tokens, "total_count": len(tokens)}

    logger.info(
        "tool_invocation_success",
        module="google_workspace",
        action="list_user_tokens",
        tool_name="google_workspace.list_user_tokens",
        total_count=len(tokens),
        api_calls=client.api_calls,
    )

    return build_success_response(
        invocation_id=invocation_id,
        data=data,
        started_at=started_at,
        external_api_calls=client.api_calls,
    )
