"""Implements github.get_branch_protection from mcp-tool-interface.yaml.

Retrieves branch protection rules for a specific branch of a repository.
Returns whether protection is enabled, required review count, required status
checks, enforce admins flag, and restrictions. Used for configuration
compliance checks.

A 404 from the GitHub API means no protection is configured — this is returned
as a success response with enabled=false, NOT as an error.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from github.client import GitHubClient
from shared.credential_handler import extract_github_credentials
from shared.error_formatting import format_validation_error, map_http_error
from shared.models import CredentialEnvelope, ToolInvocationResponse
from shared.response_builder import build_error_response, build_success_response

logger = structlog.get_logger()

definition: dict[str, Any] = {
    "tool_name": "github.get_branch_protection",
    "display_name": "Get Branch Protection",
    "description": (
        "Retrieve branch protection rules for a specific branch of a repository. "
        "Returns whether protection is enabled, required review count, required "
        "status checks, enforce admins flag, and restrictions. Used for configuration "
        "compliance checks."
    ),
    "category": "configuration",
    "input_schema": {
        "type": "object",
        "properties": {
            "repository": {
                "type": "string",
                "description": "Repository name (not full name, just the repo part).",
            },
            "branch": {
                "type": "string",
                "description": (
                    "Branch name to check. If omitted, uses the repository's default branch."
                ),
            },
        },
        "required": ["repository"],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "repository": {"type": "string"},
            "branch": {"type": "string"},
            "enabled": {"type": "boolean"},
            "required_pull_request_reviews": {
                "type": "object",
                "nullable": True,
                "properties": {
                    "required_approving_review_count": {"type": "integer"},
                    "dismiss_stale_reviews": {"type": "boolean"},
                    "require_code_owner_reviews": {"type": "boolean"},
                    "require_last_push_approval": {"type": "boolean"},
                },
            },
            "required_status_checks": {
                "type": "object",
                "nullable": True,
                "properties": {
                    "strict": {"type": "boolean"},
                    "contexts": {"type": "array", "items": {"type": "string"}},
                },
            },
            "enforce_admins": {"type": "boolean", "nullable": True},
            "restrictions": {
                "type": "object",
                "nullable": True,
                "properties": {
                    "users": {"type": "array", "items": {"type": "string"}},
                    "teams": {"type": "array", "items": {"type": "string"}},
                    "apps": {"type": "array", "items": {"type": "string"}},
                },
            },
            "required_signatures": {"type": "boolean", "nullable": True},
            "allow_force_pushes": {"type": "boolean", "nullable": True},
            "allow_deletions": {"type": "boolean", "nullable": True},
        },
    },
}


def _extract_reviews(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    """Extract required_pull_request_reviews fields from API response."""
    if raw is None:
        return None
    return {
        "required_approving_review_count": raw.get("required_approving_review_count", 0),
        "dismiss_stale_reviews": raw.get("dismiss_stale_reviews", False),
        "require_code_owner_reviews": raw.get("require_code_owner_reviews", False),
        "require_last_push_approval": raw.get("require_last_push_approval", False),
    }


def _extract_status_checks(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    """Extract required_status_checks fields from API response."""
    if raw is None:
        return None
    return {
        "strict": raw.get("strict", False),
        "contexts": raw.get("contexts", []),
    }


def _extract_restrictions(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    """Extract restrictions fields from API response."""
    if raw is None:
        return None
    return {
        "users": [u.get("login", "") for u in raw.get("users", [])],
        "teams": [t.get("slug", "") for t in raw.get("teams", [])],
        "apps": [a.get("slug", "") for a in raw.get("apps", [])],
    }


def _build_no_protection_data(repository: str, branch: str) -> dict[str, Any]:
    """Build response data for a branch with no protection configured."""
    return {
        "repository": repository,
        "branch": branch,
        "enabled": False,
        "required_pull_request_reviews": None,
        "required_status_checks": None,
        "enforce_admins": None,
        "restrictions": None,
        "required_signatures": None,
        "allow_force_pushes": None,
        "allow_deletions": None,
    }


async def execute(
    parameters: dict[str, Any],
    credentials: CredentialEnvelope,
    invocation_id: str,
    timeout_seconds: int = 30,
) -> ToolInvocationResponse:
    """Execute the github.get_branch_protection tool.

    Args:
        parameters: Tool input (repository, optional branch).
        credentials: Credential envelope with GitHub PAT and organization.
        invocation_id: Unique identifier for this invocation.
        timeout_seconds: Maximum execution time.

    Returns:
        A ToolInvocationResponse with branch protection data or error.
    """
    started_at = datetime.now(UTC)

    logger.debug(
        "tool_invocation_start",
        module="github",
        action="get_branch_protection",
        tool_name="github.get_branch_protection",
    )

    # Validate parameters
    repository = parameters.get("repository")
    if not repository or not isinstance(repository, str):
        return build_error_response(
            invocation_id=invocation_id,
            error=format_validation_error(
                "'repository' is required and must be a non-empty string."
            ),
            started_at=started_at,
        )

    branch = parameters.get("branch")

    # Extract credentials and create client
    github_creds = extract_github_credentials(credentials)

    async with GitHubClient(github_creds) as client:
        org = client.organization

        # If branch not specified, look up the repo's default branch
        if not branch:
            response = await client.get(f"/repos/{org}/{repository}")
            if response.status_code == 404:
                return build_error_response(
                    invocation_id=invocation_id,
                    error=format_validation_error(f"Repository '{org}/{repository}' not found."),
                    started_at=started_at,
                    external_api_calls=client.api_calls,
                )
            if response.status_code != 200:
                return build_error_response(
                    invocation_id=invocation_id,
                    error=map_http_error(response.status_code),
                    started_at=started_at,
                    external_api_calls=client.api_calls,
                )
            branch = response.json().get("default_branch", "main")

        # Fetch branch protection
        response = await client.get(f"/repos/{org}/{repository}/branches/{branch}/protection")

        # 404 means no protection configured — this is valid data, not an error
        if response.status_code == 404:
            data = _build_no_protection_data(repository, branch)
            logger.info(
                "tool_invocation_success",
                module="github",
                action="get_branch_protection",
                tool_name="github.get_branch_protection",
                repository=repository,
                branch=branch,
                enabled=False,
                api_calls=client.api_calls,
            )
            return build_success_response(
                invocation_id=invocation_id,
                data=data,
                started_at=started_at,
                external_api_calls=client.api_calls,
            )

        if response.status_code != 200:
            return build_error_response(
                invocation_id=invocation_id,
                error=map_http_error(response.status_code),
                started_at=started_at,
                external_api_calls=client.api_calls,
            )

        raw = response.json()

        data = {
            "repository": repository,
            "branch": branch,
            "enabled": True,
            "required_pull_request_reviews": _extract_reviews(
                raw.get("required_pull_request_reviews")
            ),
            "required_status_checks": _extract_status_checks(raw.get("required_status_checks")),
            "enforce_admins": (
                raw["enforce_admins"]["enabled"] if raw.get("enforce_admins") else None
            ),
            "restrictions": _extract_restrictions(raw.get("restrictions")),
            "required_signatures": (
                raw["required_signatures"]["enabled"] if raw.get("required_signatures") else None
            ),
            "allow_force_pushes": (
                raw["allow_force_pushes"]["enabled"] if raw.get("allow_force_pushes") else None
            ),
            "allow_deletions": (
                raw["allow_deletions"]["enabled"] if raw.get("allow_deletions") else None
            ),
        }

        logger.info(
            "tool_invocation_success",
            module="github",
            action="get_branch_protection",
            tool_name="github.get_branch_protection",
            repository=repository,
            branch=branch,
            enabled=True,
            api_calls=client.api_calls,
        )

        return build_success_response(
            invocation_id=invocation_id,
            data=data,
            started_at=started_at,
            external_api_calls=client.api_calls,
        )
