"""Implements github.list_organization_members from mcp-tool-interface.yaml.

Lists all members of the GitHub organization with their role (admin/member),
two-factor authentication status, and account metadata. Used for access reviews
and to identify organization administrators.

Role resolution: the /orgs/{org}/members endpoint does not return roles directly.
We fetch admin-filtered and member-filtered lists separately and tag each set.

2FA detection: the /orgs/{org}/members?filter=2fa_disabled endpoint returns members
without 2FA. This requires org owner permissions; if a 403 is returned, we degrade
gracefully and set two_factor_enabled to null.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from github.client import GitHubClient
from shared.credential_handler import extract_github_credentials
from shared.error_formatting import format_validation_error, map_http_error
from shared.models import CredentialEnvelope, ToolInvocationResponse
from shared.response_builder import build_error_response, build_success_response

logger = structlog.get_logger()

definition: dict[str, Any] = {
    "tool_name": "github.list_organization_members",
    "display_name": "List Organization Members",
    "description": (
        "List all members of the GitHub organization with their role "
        "(owner or member), two-factor authentication status, and account "
        "metadata. Used for access reviews and to identify organization "
        "administrators."
    ),
    "category": "identity",
    "input_schema": {
        "type": "object",
        "properties": {
            "role": {
                "type": "string",
                "enum": ["all", "admin", "member"],
                "description": "Filter by role. Default: all.",
                "default": "all",
            },
            "per_page": {
                "type": "integer",
                "description": "Results per page (max 100). Default: 100.",
                "default": 100,
                "minimum": 1,
                "maximum": 100,
            },
        },
        "required": [],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "members": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "login": {"type": "string"},
                        "id": {"type": "integer"},
                        "role": {"type": "string"},
                        "site_admin": {"type": "boolean"},
                        "two_factor_enabled": {"type": "boolean", "nullable": True},
                        "avatar_url": {"type": "string"},
                    },
                },
            },
            "total_count": {"type": "integer"},
        },
    },
    "rate_limit": {"max_calls_per_second": 5, "max_calls_per_minute": 100},
    "pagination": {
        "supported": True,
        "cursor_parameter": "page",
        "cursor_response_field": None,
    },
}

_VALID_ROLES = {"all", "admin", "member"}


async def _fetch_members_with_role(
    client: GitHubClient,
    role: str,
    per_page: int,
) -> list[dict[str, Any]]:
    """Fetch members filtered by role and tag each with their role.

    If role is "all", fetches admin and member lists separately to determine
    each member's role. Otherwise fetches the single filtered list.

    Args:
        client: Authenticated GitHub client.
        role: Role filter ("all", "admin", or "member").
        per_page: Results per page.

    Returns:
        List of member dicts, each tagged with a "role" key.

    Raises:
        httpx.HTTPStatusError: On non-2xx API responses.
    """
    members_path = f"/orgs/{client.organization}/members"

    if role == "all":
        admins = await client.get_all_pages(
            members_path, params={"role": "admin", "per_page": per_page}
        )
        for m in admins:
            m["_role"] = "admin"

        members = await client.get_all_pages(
            members_path, params={"role": "member", "per_page": per_page}
        )
        for m in members:
            m["_role"] = "member"

        return admins + members
    else:
        fetched = await client.get_all_pages(
            members_path, params={"role": role, "per_page": per_page}
        )
        for m in fetched:
            m["_role"] = role
        return fetched


async def _fetch_2fa_disabled_logins(
    client: GitHubClient,
    per_page: int,
) -> set[str] | None:
    """Fetch the set of member logins that have 2FA disabled.

    Requires org owner permissions. Returns None if the caller lacks
    permission (403), so the tool can degrade gracefully.

    Args:
        client: Authenticated GitHub client.
        per_page: Results per page.

    Returns:
        A set of login strings for members without 2FA, or None if
        the caller lacks permission to check.
    """
    members_path = f"/orgs/{client.organization}/members"
    try:
        disabled = await client.get_all_pages(
            members_path, params={"filter": "2fa_disabled", "per_page": per_page}
        )
        return {m["login"] for m in disabled}
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 403:
            logger.warning(
                "2fa_filter_forbidden",
                module="github",
                action="list_organization_members",
                tool_name="github.list_organization_members",
                detail="Cannot check 2FA status (requires org owner). Defaulting to null.",
            )
            return None
        raise


async def execute(
    parameters: dict[str, Any],
    credentials: CredentialEnvelope,
    invocation_id: str,
    timeout_seconds: int = 30,
) -> ToolInvocationResponse:
    """Execute the github.list_organization_members tool.

    Args:
        parameters: Tool input parameters (role, per_page).
        credentials: Credential envelope with GitHub PAT and organization.
        invocation_id: Unique identifier for this invocation.
        timeout_seconds: Maximum execution time.

    Returns:
        A ToolInvocationResponse with member data or error.
    """
    started_at = datetime.now(UTC)

    logger.debug(
        "tool_invocation_start",
        module="github",
        action="list_organization_members",
        tool_name="github.list_organization_members",
    )

    # Validate parameters
    role = parameters.get("role", "all")
    per_page = parameters.get("per_page", 100)

    if role not in _VALID_ROLES:
        return build_error_response(
            invocation_id=invocation_id,
            error=format_validation_error(
                f"Invalid role '{role}'. Must be one of: {', '.join(_VALID_ROLES)}."
            ),
            started_at=started_at,
        )

    if not isinstance(per_page, int) or not 1 <= per_page <= 100:
        return build_error_response(
            invocation_id=invocation_id,
            error=format_validation_error("per_page must be an integer between 1 and 100."),
            started_at=started_at,
        )

    # Extract credentials and create client
    github_creds = extract_github_credentials(credentials)

    async with GitHubClient(github_creds) as client:
        try:
            raw_members = await _fetch_members_with_role(client, role, per_page)
        except httpx.HTTPStatusError as exc:
            return build_error_response(
                invocation_id=invocation_id,
                error=map_http_error(exc.response.status_code),
                started_at=started_at,
                external_api_calls=client.api_calls,
            )

        # Fetch 2FA disabled list (may return None if non-owner)
        try:
            disabled_logins = await _fetch_2fa_disabled_logins(client, per_page)
        except httpx.HTTPStatusError as exc:
            return build_error_response(
                invocation_id=invocation_id,
                error=map_http_error(exc.response.status_code),
                started_at=started_at,
                external_api_calls=client.api_calls,
            )

        # Build member list with role and 2FA status
        members = []
        for raw in raw_members:
            login = raw.get("login", "")
            if disabled_logins is not None:
                two_factor_enabled = login not in disabled_logins
            else:
                two_factor_enabled = None

            members.append(
                {
                    "login": login,
                    "id": raw.get("id"),
                    "role": raw.get("_role", "member"),
                    "site_admin": raw.get("site_admin", False),
                    "two_factor_enabled": two_factor_enabled,
                    "avatar_url": raw.get("avatar_url", ""),
                }
            )

        data = {
            "members": members,
            "total_count": len(members),
        }

        logger.info(
            "tool_invocation_success",
            module="github",
            action="list_organization_members",
            tool_name="github.list_organization_members",
            total_count=len(members),
            api_calls=client.api_calls,
        )

        return build_success_response(
            invocation_id=invocation_id,
            data=data,
            started_at=started_at,
            external_api_calls=client.api_calls,
        )
