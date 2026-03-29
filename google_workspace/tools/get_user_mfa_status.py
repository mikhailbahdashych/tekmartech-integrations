"""Implements google_workspace.get_user_mfa_status from mcp-tool-interface.yaml.

Retrieves MFA enrollment and enforcement status for users. Returns only
identity and MFA fields for quick compliance checks, not full user profiles.
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
from shared.models import CredentialEnvelope, ToolInvocationResponse
from shared.response_builder import build_error_response, build_success_response

logger = structlog.get_logger()

definition: dict[str, Any] = {
    "tool_name": "google_workspace.get_user_mfa_status",
    "display_name": "User MFA Status",
    "description": (
        "Retrieve MFA enrollment and enforcement status for users. Indicates "
        "whether 2-step verification is enrolled, enforced, or disabled."
    ),
    "category": "access_management",
    "input_schema": {
        "type": "object",
        "properties": {
            "user_key": {
                "type": "string",
                "description": (
                    "Specific user email to check. If omitted, returns MFA status for all users."
                ),
            },
        },
        "required": [],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "mfa_statuses": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "primary_email": {"type": "string"},
                        "is_enrolled_in_2sv": {"type": "boolean"},
                        "is_enforced_in_2sv": {"type": "boolean"},
                        "last_login_time": {
                            "type": "string",
                            "format": "date-time",
                            "nullable": True,
                        },
                    },
                },
            },
            "total_count": {"type": "integer"},
        },
    },
}


def _extract_mfa_status(raw: dict[str, Any]) -> dict[str, Any]:
    """Extract MFA-relevant fields from a Google Directory user resource."""
    return {
        "primary_email": raw.get("primaryEmail", ""),
        "is_enrolled_in_2sv": raw.get("isEnrolledIn2Sv", False),
        "is_enforced_in_2sv": raw.get("isEnforcedIn2Sv", False),
        "last_login_time": raw.get("lastLoginTime"),
    }


async def execute(
    parameters: dict[str, Any],
    credentials: CredentialEnvelope,
    invocation_id: str,
    timeout_seconds: int = 30,
) -> ToolInvocationResponse:
    """Execute the google_workspace.get_user_mfa_status tool.

    Args:
        parameters: Tool input (optional user_key).
        credentials: Credential envelope with Google service account.
        invocation_id: Unique identifier for this invocation.
        timeout_seconds: Maximum execution time.

    Returns:
        A ToolInvocationResponse with MFA status data or error.
    """
    started_at = datetime.now(UTC)

    logger.debug(
        "tool_invocation_start",
        module="google_workspace",
        action="get_user_mfa_status",
        tool_name="google_workspace.get_user_mfa_status",
    )

    gw_creds = extract_google_workspace_credentials(credentials)
    client = GoogleWorkspaceClient(gw_creds)
    directory = client.directory_service()

    user_key = parameters.get("user_key")
    statuses: list[dict[str, Any]] = []

    try:
        if user_key:
            # Single user lookup
            request = directory.users().get(userKey=user_key, projection="full")
            response = await run_google_api(client, request.execute)
            statuses.append(_extract_mfa_status(response))
        else:
            # All users with pagination
            page_token: str | None = None
            while True:
                kwargs: dict[str, Any] = {
                    "customer": "my_customer",
                    "maxResults": 500,
                    "projection": "full",
                }
                if page_token:
                    kwargs["pageToken"] = page_token

                request = directory.users().list(**kwargs)
                response = await run_google_api(client, request.execute)

                for raw_user in response.get("users", []):
                    statuses.append(_extract_mfa_status(raw_user))

                page_token = response.get("nextPageToken")
                if not page_token:
                    break

    except HttpError as exc:
        return build_error_response(
            invocation_id=invocation_id,
            error=handle_google_error(exc),
            started_at=started_at,
            external_api_calls=client.api_calls,
        )

    data = {"mfa_statuses": statuses, "total_count": len(statuses)}

    logger.info(
        "tool_invocation_success",
        module="google_workspace",
        action="get_user_mfa_status",
        tool_name="google_workspace.get_user_mfa_status",
        total_count=len(statuses),
        api_calls=client.api_calls,
    )

    return build_success_response(
        invocation_id=invocation_id,
        data=data,
        started_at=started_at,
        external_api_calls=client.api_calls,
    )
