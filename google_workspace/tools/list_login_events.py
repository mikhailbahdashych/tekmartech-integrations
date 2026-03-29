"""Implements google_workspace.list_login_events from mcp-tool-interface.yaml.

Retrieves login activity events from the Google Workspace Admin Reports API.
Includes successful logins, failed attempts, and suspicious activity flags.
Parses Google's nested event parameter format into flat objects.
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
    "tool_name": "google_workspace.list_login_events",
    "display_name": "Login Activity Events",
    "description": (
        "Retrieve login activity events from the Google Workspace Admin Reports "
        "API. Includes successful logins, failed attempts, and suspicious "
        "activity flags."
    ),
    "category": "audit_log",
    "input_schema": {
        "type": "object",
        "properties": {
            "user_key": {
                "type": "string",
                "description": "Filter to specific user email. Default: 'all'.",
                "default": "all",
            },
            "start_time": {
                "type": "string",
                "format": "date-time",
                "description": "Start of time range (ISO 8601 / RFC 3339).",
            },
            "end_time": {
                "type": "string",
                "format": "date-time",
                "description": "End of time range (ISO 8601 / RFC 3339).",
            },
            "event_name": {
                "type": "string",
                "description": (
                    "Filter by event name (e.g. 'login_success', "
                    "'login_failure', 'suspicious_login')."
                ),
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum events to return. Default: 100.",
                "default": 100,
                "minimum": 1,
                "maximum": 1000,
            },
        },
        "required": [],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "events": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "actor_email": {"type": "string"},
                        "event_name": {"type": "string"},
                        "ip_address": {"type": "string", "nullable": True},
                        "login_timestamp": {"type": "string", "format": "date-time"},
                        "login_type": {"type": "string", "nullable": True},
                        "is_suspicious": {"type": "boolean"},
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


def _parse_event_parameters(params: list[dict[str, Any]]) -> dict[str, Any]:
    """Parse Google's nested event parameters into a flat dict.

    Google Reports events have parameters as [{name: str, value: str}, ...].
    This flattens them into {name: value}.

    Args:
        params: List of parameter dicts from the Google Reports API.

    Returns:
        A flat dict of parameter name to value.
    """
    result: dict[str, Any] = {}
    for p in params:
        name = p.get("name", "")
        # Google uses different value keys: value, intValue, boolValue, multiValue
        value = p.get("value") or p.get("intValue") or p.get("boolValue") or p.get("multiValue")
        result[name] = value
    return result


def _extract_login_event(activity: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract login events from a Google Reports activity item.

    Each activity can contain multiple events in its 'events' array.

    Args:
        activity: A single activity item from the Reports API.

    Returns:
        List of extracted login event dicts.
    """
    actor = activity.get("actor", {})
    actor_email = actor.get("email", "")
    ip_address = activity.get("ipAddress")
    timestamp = activity.get("id", {}).get("time", "")

    events = []
    for event in activity.get("events", []):
        event_name = event.get("name", "")
        params = _parse_event_parameters(event.get("parameters", []))

        events.append(
            {
                "actor_email": actor_email,
                "event_name": event_name,
                "ip_address": ip_address,
                "login_timestamp": timestamp,
                "login_type": params.get("login_type"),
                "is_suspicious": event_name in ("suspicious_login", "gov_attack_warning"),
            }
        )
    return events


async def execute(
    parameters: dict[str, Any],
    credentials: CredentialEnvelope,
    invocation_id: str,
    timeout_seconds: int = 30,
) -> ToolInvocationResponse:
    """Execute the google_workspace.list_login_events tool.

    Args:
        parameters: Tool input (user_key, start_time, end_time, event_name, max_results).
        credentials: Credential envelope with Google service account.
        invocation_id: Unique identifier for this invocation.
        timeout_seconds: Maximum execution time.

    Returns:
        A ToolInvocationResponse with login event data or error.
    """
    started_at = datetime.now(UTC)

    logger.debug(
        "tool_invocation_start",
        module="google_workspace",
        action="list_login_events",
        tool_name="google_workspace.list_login_events",
    )

    user_key = parameters.get("user_key", "all")
    max_results = parameters.get("max_results", 100)

    if not isinstance(max_results, int) or not 1 <= max_results <= 1000:
        return build_error_response(
            invocation_id=invocation_id,
            error=format_validation_error("max_results must be an integer between 1 and 1000."),
            started_at=started_at,
        )

    # Validate time range if provided
    start_time = parameters.get("start_time")
    end_time = parameters.get("end_time")
    if start_time:
        try:
            datetime.fromisoformat(start_time)
        except (ValueError, TypeError):
            return build_error_response(
                invocation_id=invocation_id,
                error=format_validation_error(f"Invalid start_time format: {start_time}"),
                started_at=started_at,
            )
    if end_time:
        try:
            datetime.fromisoformat(end_time)
        except (ValueError, TypeError):
            return build_error_response(
                invocation_id=invocation_id,
                error=format_validation_error(f"Invalid end_time format: {end_time}"),
                started_at=started_at,
            )

    gw_creds = extract_google_workspace_credentials(credentials)
    client = GoogleWorkspaceClient(gw_creds)
    reports = client.reports_service()

    all_events: list[dict[str, Any]] = []
    page_token: str | None = None

    try:
        while True:
            kwargs: dict[str, Any] = {
                "userKey": user_key,
                "applicationName": "login",
                "maxResults": min(max_results, 1000),
            }
            if start_time:
                kwargs["startTime"] = start_time
            if end_time:
                kwargs["endTime"] = end_time
            if "event_name" in parameters:
                kwargs["eventName"] = parameters["event_name"]
            if page_token:
                kwargs["pageToken"] = page_token

            request = reports.activities().list(**kwargs)
            response = await run_google_api(client, request.execute)

            for activity in response.get("items", []):
                all_events.extend(_extract_login_event(activity))

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

    data = {"events": all_events, "total_count": len(all_events)}

    logger.info(
        "tool_invocation_success",
        module="google_workspace",
        action="list_login_events",
        tool_name="google_workspace.list_login_events",
        total_count=len(all_events),
        api_calls=client.api_calls,
    )

    return build_success_response(
        invocation_id=invocation_id,
        data=data,
        started_at=started_at,
        external_api_calls=client.api_calls,
    )
