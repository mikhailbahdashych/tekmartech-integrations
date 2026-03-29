"""Implements google_workspace.list_users from mcp-tool-interface.yaml.

Lists all users in the Google Workspace directory with their profile
information, organizational unit, and account status. Uses nextPageToken
pagination for complete listing.
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
    "tool_name": "google_workspace.list_users",
    "display_name": "List Workspace Users",
    "description": (
        "List all users in the Google Workspace directory with their profile "
        "information, organizational unit, and account status."
    ),
    "category": "identity",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Google Directory API query syntax for filtering "
                    "(e.g. 'orgUnitPath=/Engineering')."
                ),
            },
            "show_deleted": {
                "type": "boolean",
                "description": "Include deleted users. Default: false.",
                "default": False,
            },
        },
        "required": [],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "users": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "primary_email": {"type": "string"},
                        "full_name": {"type": "string"},
                        "org_unit_path": {"type": "string"},
                        "is_admin": {"type": "boolean"},
                        "is_delegated_admin": {"type": "boolean"},
                        "suspended": {"type": "boolean"},
                        "archived": {"type": "boolean"},
                        "creation_time": {"type": "string", "format": "date-time"},
                        "last_login_time": {
                            "type": "string",
                            "format": "date-time",
                            "nullable": True,
                        },
                        "is_enrolled_in_2sv": {"type": "boolean"},
                        "is_enforced_in_2sv": {"type": "boolean"},
                    },
                },
            },
            "total_count": {"type": "integer"},
        },
    },
    "pagination": {
        "supported": True,
        "cursor_parameter": "pageToken",
        "cursor_response_field": "nextPageToken",
    },
}


def _extract_user(raw: dict[str, Any]) -> dict[str, Any]:
    """Extract relevant fields from a Google Directory user resource."""
    name = raw.get("name", {})
    return {
        "primary_email": raw.get("primaryEmail", ""),
        "full_name": name.get("fullName", ""),
        "org_unit_path": raw.get("orgUnitPath", "/"),
        "is_admin": raw.get("isAdmin", False),
        "is_delegated_admin": raw.get("isDelegatedAdmin", False),
        "suspended": raw.get("suspended", False),
        "archived": raw.get("archived", False),
        "creation_time": raw.get("creationTime"),
        "last_login_time": raw.get("lastLoginTime"),
        "is_enrolled_in_2sv": raw.get("isEnrolledIn2Sv", False),
        "is_enforced_in_2sv": raw.get("isEnforcedIn2Sv", False),
    }


async def execute(
    parameters: dict[str, Any],
    credentials: CredentialEnvelope,
    invocation_id: str,
    timeout_seconds: int = 30,
) -> ToolInvocationResponse:
    """Execute the google_workspace.list_users tool.

    Args:
        parameters: Tool input (query, show_deleted).
        credentials: Credential envelope with Google service account.
        invocation_id: Unique identifier for this invocation.
        timeout_seconds: Maximum execution time.

    Returns:
        A ToolInvocationResponse with user data or error.
    """
    started_at = datetime.now(UTC)

    logger.debug(
        "tool_invocation_start",
        module="google_workspace",
        action="list_users",
        tool_name="google_workspace.list_users",
    )

    gw_creds = extract_google_workspace_credentials(credentials)
    client = GoogleWorkspaceClient(gw_creds)
    directory = client.directory_service()

    query = parameters.get("query")
    show_deleted = parameters.get("show_deleted", False)

    all_users: list[dict[str, Any]] = []
    page_token: str | None = None

    try:
        while True:
            kwargs: dict[str, Any] = {
                "customer": "my_customer",
                "maxResults": 500,
                "projection": "full",
                "showDeleted": str(show_deleted).lower(),
            }
            if query:
                kwargs["query"] = query
            if page_token:
                kwargs["pageToken"] = page_token

            request = directory.users().list(**kwargs)
            response = await run_google_api(client, request.execute)

            for raw_user in response.get("users", []):
                all_users.append(_extract_user(raw_user))

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

    data = {"users": all_users, "total_count": len(all_users)}

    logger.info(
        "tool_invocation_success",
        module="google_workspace",
        action="list_users",
        tool_name="google_workspace.list_users",
        total_count=len(all_users),
        api_calls=client.api_calls,
    )

    return build_success_response(
        invocation_id=invocation_id,
        data=data,
        started_at=started_at,
        external_api_calls=client.api_calls,
    )
