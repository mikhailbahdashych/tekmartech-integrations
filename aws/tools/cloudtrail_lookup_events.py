"""Implements aws.cloudtrail_lookup_events from mcp-tool-interface.yaml.

Searches CloudTrail events by time range, event type, resource, or user identity.
Returns management events. Uses NextToken pagination.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from botocore.exceptions import ClientError

from aws.client import AWSClient, handle_client_error, run_boto3
from shared.credential_handler import extract_aws_credentials
from shared.error_formatting import format_validation_error
from shared.models import CredentialEnvelope, ToolInvocationResponse
from shared.response_builder import build_error_response, build_success_response

logger = structlog.get_logger()

definition: dict[str, Any] = {
    "tool_name": "aws.cloudtrail_lookup_events",
    "display_name": "CloudTrail Event Lookup",
    "description": (
        "Search CloudTrail events by time range, event type, resource, or user "
        "identity. Returns management events and optionally data events."
    ),
    "category": "audit_log",
    "input_schema": {
        "type": "object",
        "properties": {
            "start_time": {
                "type": "string",
                "format": "date-time",
                "description": "Start of time range (ISO 8601). Default: 24 hours ago.",
            },
            "end_time": {
                "type": "string",
                "format": "date-time",
                "description": "End of time range (ISO 8601). Default: now.",
            },
            "event_name": {
                "type": "string",
                "description": "Filter by event name (e.g. 'ConsoleLogin').",
            },
            "resource_type": {
                "type": "string",
                "description": "Filter by resource type (e.g. 'AWS::S3::Bucket').",
            },
            "username": {
                "type": "string",
                "description": "Filter by username.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum events to return per page. Default: 50, max: 50.",
                "default": 50,
                "minimum": 1,
                "maximum": 50,
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
                        "event_id": {"type": "string"},
                        "event_time": {"type": "string", "format": "date-time"},
                        "event_name": {"type": "string"},
                        "event_source": {"type": "string"},
                        "username": {"type": "string", "nullable": True},
                        "resources": {"type": "array", "items": {"type": "object"}},
                        "cloud_trail_event": {"type": "object"},
                    },
                },
            },
            "total_count": {"type": "integer"},
        },
    },
}


def _parse_iso_datetime(value: str) -> datetime:
    """Parse an ISO 8601 datetime string to a timezone-aware datetime."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


async def execute(
    parameters: dict[str, Any],
    credentials: CredentialEnvelope,
    invocation_id: str,
    timeout_seconds: int = 30,
) -> ToolInvocationResponse:
    """Execute the aws.cloudtrail_lookup_events tool.

    Args:
        parameters: Tool input (start_time, end_time, event_name, etc.).
        credentials: Credential envelope with AWS credentials.
        invocation_id: Unique identifier for this invocation.
        timeout_seconds: Maximum execution time.

    Returns:
        A ToolInvocationResponse with CloudTrail events or error.
    """
    started_at = datetime.now(UTC)

    logger.debug(
        "tool_invocation_start",
        module="aws",
        action="cloudtrail_lookup_events",
        tool_name="aws.cloudtrail_lookup_events",
    )

    # Parse time range
    now = datetime.now(UTC)
    try:
        end_time = _parse_iso_datetime(parameters["end_time"]) if "end_time" in parameters else now
        start_time = (
            _parse_iso_datetime(parameters["start_time"])
            if "start_time" in parameters
            else end_time - timedelta(hours=24)
        )
    except (ValueError, TypeError) as exc:
        return build_error_response(
            invocation_id=invocation_id,
            error=format_validation_error(f"Invalid datetime format: {exc}"),
            started_at=started_at,
        )

    max_results = parameters.get("max_results", 50)
    if not isinstance(max_results, int) or not 1 <= max_results <= 50:
        return build_error_response(
            invocation_id=invocation_id,
            error=format_validation_error("max_results must be an integer between 1 and 50."),
            started_at=started_at,
        )

    # Build lookup attributes
    lookup_attrs: list[dict[str, str]] = []
    if "event_name" in parameters:
        lookup_attrs.append(
            {"AttributeKey": "EventName", "AttributeValue": parameters["event_name"]}
        )
    if "resource_type" in parameters:
        lookup_attrs.append(
            {"AttributeKey": "ResourceType", "AttributeValue": parameters["resource_type"]}
        )
    if "username" in parameters:
        lookup_attrs.append({"AttributeKey": "Username", "AttributeValue": parameters["username"]})

    aws_creds = extract_aws_credentials(credentials)
    client = AWSClient(aws_creds)
    ct = client.cloudtrail_client()

    try:
        kwargs: dict[str, Any] = {
            "StartTime": start_time,
            "EndTime": end_time,
            "MaxResults": max_results,
        }
        if lookup_attrs:
            kwargs["LookupAttributes"] = lookup_attrs

        all_events: list[dict[str, Any]] = []
        while True:
            response = await run_boto3(client, ct.lookup_events, **kwargs)
            for event in response.get("Events", []):
                # Parse the CloudTrailEvent JSON string
                raw_ct_event = event.get("CloudTrailEvent", "{}")
                try:
                    ct_event = json.loads(raw_ct_event)
                except (json.JSONDecodeError, TypeError):
                    ct_event = {}

                all_events.append(
                    {
                        "event_id": event.get("EventId"),
                        "event_time": event.get("EventTime", "").isoformat()
                        if event.get("EventTime")
                        else None,
                        "event_name": event.get("EventName"),
                        "event_source": event.get("EventSource"),
                        "username": event.get("Username"),
                        "resources": [
                            {
                                "resource_type": r.get("ResourceType"),
                                "resource_name": r.get("ResourceName"),
                            }
                            for r in event.get("Resources", [])
                        ],
                        "cloud_trail_event": ct_event,
                    }
                )

            next_token = response.get("NextToken")
            if not next_token:
                break
            kwargs["NextToken"] = next_token

    except ClientError as exc:
        return build_error_response(
            invocation_id=invocation_id,
            error=handle_client_error(exc),
            started_at=started_at,
            external_api_calls=client.api_calls,
        )

    data = {"events": all_events, "total_count": len(all_events)}

    logger.info(
        "tool_invocation_success",
        module="aws",
        action="cloudtrail_lookup_events",
        tool_name="aws.cloudtrail_lookup_events",
        total_count=len(all_events),
        api_calls=client.api_calls,
    )

    return build_success_response(
        invocation_id=invocation_id,
        data=data,
        started_at=started_at,
        external_api_calls=client.api_calls,
    )
