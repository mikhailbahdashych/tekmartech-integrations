"""Google API client creation from per-invocation service account credentials.

Creates authenticated Google API service objects for the Admin SDK Directory
and Reports APIs. Uses domain-wide delegation when delegated_email is provided.

Since google-api-python-client uses synchronous HTTP, all API calls must be
wrapped with asyncio.to_thread() to avoid blocking the event loop.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import structlog
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from shared.error_formatting import map_google_api_error, sanitize_error_message
from shared.models import GoogleWorkspaceCredentials, ToolInvocationError

logger = structlog.get_logger()

GOOGLE_WORKSPACE_SCOPES = [
    "https://www.googleapis.com/auth/admin.directory.user.readonly",
    "https://www.googleapis.com/auth/admin.directory.user.security",
    "https://www.googleapis.com/auth/admin.reports.audit.readonly",
]


class GoogleWorkspaceClient:
    """Authenticated Google API client wrapper for read-only Workspace operations.

    Creates service account credentials, optionally with domain-wide delegation,
    and provides service object accessors. Tracks API call counts.

    Args:
        credentials: Google Workspace credentials (service account JSON + optional delegated email).
    """

    def __init__(self, credentials: GoogleWorkspaceCredentials) -> None:
        sa_info = json.loads(credentials.service_account_json)
        creds = Credentials.from_service_account_info(sa_info, scopes=GOOGLE_WORKSPACE_SCOPES)

        if credentials.delegated_email:
            creds = creds.with_subject(credentials.delegated_email)

        self._credentials = creds
        self._api_calls = 0
        self._timeout = int(os.environ.get("GOOGLE_API_TIMEOUT", "30"))

    @property
    def api_calls(self) -> int:
        """Total number of external API calls made by this client."""
        return self._api_calls

    def _increment_calls(self, count: int = 1) -> None:
        """Increment the API call counter."""
        self._api_calls += count

    def directory_service(self) -> Any:
        """Build an Admin SDK Directory API v1 service object."""
        return build("admin", "directory_v1", credentials=self._credentials)

    def reports_service(self) -> Any:
        """Build an Admin SDK Reports API v1 service object."""
        return build("admin", "reports_v1", credentials=self._credentials)


# Set to False in tests to skip asyncio.to_thread (mock compatibility).
_use_thread: bool = True


async def run_google_api(
    client: GoogleWorkspaceClient, func: Any, *args: Any, **kwargs: Any
) -> Any:
    """Run a synchronous Google API call, optionally in a thread.

    In production, uses asyncio.to_thread to avoid blocking the event loop.
    In tests, calls directly for mock compatibility.

    Args:
        client: The GoogleWorkspaceClient instance (for call counting).
        func: The callable to invoke (e.g. service.users().list().execute).
        *args: Positional arguments.
        **kwargs: Keyword arguments.

    Returns:
        The Google API response dict.

    Raises:
        googleapiclient.errors.HttpError: On Google API errors.
    """
    client._increment_calls()
    logger.debug(
        "google_api_call",
        module="google_workspace",
        action="api_call",
        method=getattr(func, "__name__", str(func)),
        api_call_number=client.api_calls,
    )
    if _use_thread:
        return await asyncio.to_thread(func, *args, **kwargs)
    return func(*args, **kwargs)


def handle_google_error(exc: HttpError) -> ToolInvocationError:
    """Map a Google API HttpError to a contract ToolInvocationError.

    Args:
        exc: The google-api-python-client HttpError exception.

    Returns:
        A ToolInvocationError with the appropriate error code.
    """
    status_code = exc.resp.status if exc.resp else 500
    message = sanitize_error_message(str(exc))
    return map_google_api_error(status_code, message)
