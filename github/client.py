"""Authenticated HTTP client for the GitHub REST API.

Creates an httpx.AsyncClient with the PAT in the Authorization header.
All methods are read-only GET requests. The client tracks the number of
API calls made for metadata reporting.

The base URL is configurable via the GITHUB_API_BASE_URL environment variable
(default: https://api.github.com).
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import structlog

from shared.models import GitHubCredentials
from shared.pagination import get_next_url

logger = structlog.get_logger()

_DEFAULT_BASE_URL = "https://api.github.com"


class GitHubClient:
    """Async HTTP client for read-only GitHub REST API operations.

    Wraps httpx.AsyncClient with GitHub authentication headers,
    API call counting, and Link header pagination support.

    Args:
        credentials: GitHub credentials (PAT + organization).
        base_url: Override the GitHub API base URL (for testing).
    """

    def __init__(
        self,
        credentials: GitHubCredentials,
        base_url: str | None = None,
    ) -> None:
        self._organization = credentials.organization
        self._api_calls = 0
        resolved_base_url = base_url or os.environ.get("GITHUB_API_BASE_URL", _DEFAULT_BASE_URL)
        self._client = httpx.AsyncClient(
            base_url=resolved_base_url,
            headers={
                "Authorization": f"Bearer {credentials.personal_access_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "tekmar-github-mcp/0.1.0",
            },
            timeout=30.0,
        )

    @property
    def organization(self) -> str:
        """The GitHub organization this client queries against."""
        return self._organization

    @property
    def api_calls(self) -> int:
        """Total number of external API calls made by this client."""
        return self._api_calls

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Make an authenticated GET request to the GitHub API.

        Does NOT raise on HTTP errors — callers handle status codes for
        context-specific logic (e.g. 404 on branch protection is not an error).

        Args:
            path: Relative API path (e.g. /orgs/{org}/members) or absolute URL.
            params: Optional query parameters.

        Returns:
            The httpx.Response object.
        """
        self._api_calls += 1
        response = await self._client.get(path, params=params)
        logger.debug(
            "github_api_call",
            module="github",
            action="api_call",
            path=path,
            status_code=response.status_code,
            api_call_number=self._api_calls,
        )
        return response

    async def get_all_pages(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch all pages from a paginated GitHub API endpoint.

        Follows Link header pagination to completion. The first request uses
        the given path and params; subsequent requests use the absolute URL
        from the Link header (which includes query parameters).

        Args:
            path: Relative API path for the first request.
            params: Optional query parameters for the first request.

        Returns:
            A list of all items across all pages.

        Raises:
            httpx.HTTPStatusError: On non-2xx responses.
        """
        all_items: list[dict[str, Any]] = []
        request_params = dict(params or {})
        if "per_page" not in request_params:
            request_params["per_page"] = 100

        # First request: relative path with params
        response = await self.get(path, params=request_params)
        if response.status_code != 200:
            response.raise_for_status()
        all_items.extend(response.json())

        # Subsequent requests: absolute URL from Link header (params baked in)
        next_url = get_next_url(response.headers.get("link"))
        while next_url:
            self._api_calls += 1
            response = await self._client.get(next_url)
            logger.debug(
                "github_api_call",
                module="github",
                action="paginate",
                url=next_url,
                status_code=response.status_code,
                api_call_number=self._api_calls,
            )
            if response.status_code != 200:
                response.raise_for_status()
            all_items.extend(response.json())
            next_url = get_next_url(response.headers.get("link"))

        return all_items

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> GitHubClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
