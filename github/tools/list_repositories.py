"""Implements github.list_repositories from mcp-tool-interface.yaml.

Lists all repositories in the organization with their visibility, default branch,
creation date, last push date, and language. Used to identify public repositories,
inactive repositories, and to scope subsequent per-repository queries.
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
    "tool_name": "github.list_repositories",
    "display_name": "List Repositories",
    "description": (
        "List all repositories in the organization with their visibility "
        "(public, private, internal), default branch, creation date, last push "
        "date, and language. Used to identify public repositories, inactive "
        "repositories, and to scope subsequent per-repository queries."
    ),
    "category": "configuration",
    "input_schema": {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": ["all", "public", "private", "forks", "sources"],
                "description": "Filter by repository type. Default: all.",
                "default": "all",
            },
            "sort": {
                "type": "string",
                "enum": ["created", "updated", "pushed", "full_name"],
                "description": "Sort field. Default: created.",
                "default": "created",
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
            "repositories": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "full_name": {"type": "string"},
                        "visibility": {"type": "string"},
                        "private": {"type": "boolean"},
                        "default_branch": {"type": "string"},
                        "language": {"type": "string", "nullable": True},
                        "created_at": {"type": "string", "format": "date-time"},
                        "updated_at": {"type": "string", "format": "date-time"},
                        "pushed_at": {
                            "type": "string",
                            "format": "date-time",
                            "nullable": True,
                        },
                        "size": {"type": "integer"},
                        "archived": {"type": "boolean"},
                        "disabled": {"type": "boolean"},
                        "open_issues_count": {"type": "integer"},
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

_VALID_TYPES = {"all", "public", "private", "forks", "sources"}
_VALID_SORTS = {"created", "updated", "pushed", "full_name"}


async def execute(
    parameters: dict[str, Any],
    credentials: CredentialEnvelope,
    invocation_id: str,
    timeout_seconds: int = 30,
) -> ToolInvocationResponse:
    """Execute the github.list_repositories tool.

    Args:
        parameters: Tool input parameters (type, sort, per_page).
        credentials: Credential envelope with GitHub PAT and organization.
        invocation_id: Unique identifier for this invocation.
        timeout_seconds: Maximum execution time.

    Returns:
        A ToolInvocationResponse with repository data or error.
    """
    started_at = datetime.now(UTC)

    logger.debug(
        "tool_invocation_start",
        module="github",
        action="list_repositories",
        tool_name="github.list_repositories",
    )

    # Validate parameters
    repo_type = parameters.get("type", "all")
    sort = parameters.get("sort", "created")
    per_page = parameters.get("per_page", 100)

    if repo_type not in _VALID_TYPES:
        return build_error_response(
            invocation_id=invocation_id,
            error=format_validation_error(
                f"Invalid type '{repo_type}'. Must be one of: {', '.join(_VALID_TYPES)}."
            ),
            started_at=started_at,
        )

    if sort not in _VALID_SORTS:
        return build_error_response(
            invocation_id=invocation_id,
            error=format_validation_error(
                f"Invalid sort '{sort}'. Must be one of: {', '.join(_VALID_SORTS)}."
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
            query_params: dict[str, Any] = {
                "type": repo_type,
                "sort": sort,
                "per_page": per_page,
            }
            raw_repos = await client.get_all_pages(
                f"/orgs/{client.organization}/repos",
                params=query_params,
            )
        except httpx.HTTPStatusError as exc:
            return build_error_response(
                invocation_id=invocation_id,
                error=map_http_error(exc.response.status_code),
                started_at=started_at,
                external_api_calls=client.api_calls,
            )

        repositories = [
            {
                "name": repo.get("name"),
                "full_name": repo.get("full_name"),
                "visibility": repo.get("visibility", "private"),
                "private": repo.get("private", True),
                "default_branch": repo.get("default_branch", "main"),
                "language": repo.get("language"),
                "created_at": repo.get("created_at"),
                "updated_at": repo.get("updated_at"),
                "pushed_at": repo.get("pushed_at"),
                "size": repo.get("size", 0),
                "archived": repo.get("archived", False),
                "disabled": repo.get("disabled", False),
                "open_issues_count": repo.get("open_issues_count", 0),
            }
            for repo in raw_repos
        ]

        data = {
            "repositories": repositories,
            "total_count": len(repositories),
        }

        logger.info(
            "tool_invocation_success",
            module="github",
            action="list_repositories",
            tool_name="github.list_repositories",
            total_count=len(repositories),
            api_calls=client.api_calls,
        )

        return build_success_response(
            invocation_id=invocation_id,
            data=data,
            started_at=started_at,
            external_api_calls=client.api_calls,
        )
