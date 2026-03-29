"""Implements aws.iam_list_roles from mcp-tool-interface.yaml.

Lists all IAM roles with their trust policies and attached permission policies.
Uses boto3 paginators for complete listing.
"""

from __future__ import annotations

from datetime import UTC, datetime
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
    "tool_name": "aws.iam_list_roles",
    "display_name": "List IAM Roles",
    "description": (
        "List all IAM roles with their trust policies and attached permission policies."
    ),
    "category": "access_management",
    "input_schema": {
        "type": "object",
        "properties": {
            "path_prefix": {
                "type": "string",
                "description": "Filter roles by IAM path prefix. Default '/' (all roles).",
                "default": "/",
            },
        },
        "required": [],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "roles": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "role_name": {"type": "string"},
                        "role_id": {"type": "string"},
                        "arn": {"type": "string"},
                        "path": {"type": "string"},
                        "created_at": {"type": "string", "format": "date-time"},
                        "assume_role_policy_document": {"type": "object"},
                        "max_session_duration": {"type": "integer"},
                        "attached_policies": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "policy_name": {"type": "string"},
                                    "policy_arn": {"type": "string"},
                                },
                            },
                        },
                    },
                },
            },
            "total_count": {"type": "integer"},
        },
    },
}


async def _list_all_roles(client: AWSClient, iam: Any, path_prefix: str) -> list[dict[str, Any]]:
    """Fetch all IAM roles using paginator."""
    paginator = iam.get_paginator("list_roles")

    def _paginate() -> list[dict[str, Any]]:
        roles: list[dict[str, Any]] = []
        for page in paginator.paginate(PathPrefix=path_prefix):
            client._increment_calls()
            roles.extend(page.get("Roles", []))
        return roles

    return await run_boto3(client, lambda: _paginate())


async def execute(
    parameters: dict[str, Any],
    credentials: CredentialEnvelope,
    invocation_id: str,
    timeout_seconds: int = 30,
) -> ToolInvocationResponse:
    """Execute the aws.iam_list_roles tool.

    Args:
        parameters: Tool input (path_prefix).
        credentials: Credential envelope with AWS credentials.
        invocation_id: Unique identifier for this invocation.
        timeout_seconds: Maximum execution time.

    Returns:
        A ToolInvocationResponse with role data or error.
    """
    started_at = datetime.now(UTC)

    logger.debug(
        "tool_invocation_start",
        module="aws",
        action="iam_list_roles",
        tool_name="aws.iam_list_roles",
    )

    path_prefix = parameters.get("path_prefix", "/")
    if not isinstance(path_prefix, str) or not path_prefix.startswith("/"):
        return build_error_response(
            invocation_id=invocation_id,
            error=format_validation_error("path_prefix must be a string starting with '/'."),
            started_at=started_at,
        )

    aws_creds = extract_aws_credentials(credentials)
    client = AWSClient(aws_creds)
    iam = client.iam_client()

    try:
        raw_roles = await _list_all_roles(client, iam, path_prefix)
    except ClientError as exc:
        return build_error_response(
            invocation_id=invocation_id,
            error=handle_client_error(exc),
            started_at=started_at,
            external_api_calls=client.api_calls,
        )

    roles = []
    try:
        for raw in raw_roles:
            role_name = raw.get("RoleName", "")
            # Get attached policies for this role
            attached_resp = await run_boto3(
                client,
                iam.list_attached_role_policies,
                RoleName=role_name,
            )
            attached = [
                {
                    "policy_name": p.get("PolicyName"),
                    "policy_arn": p.get("PolicyArn"),
                }
                for p in attached_resp.get("AttachedPolicies", [])
            ]

            roles.append(
                {
                    "role_name": role_name,
                    "role_id": raw.get("RoleId"),
                    "arn": raw.get("Arn"),
                    "path": raw.get("Path"),
                    "created_at": raw.get("CreateDate", "").isoformat()
                    if raw.get("CreateDate")
                    else None,
                    "assume_role_policy_document": raw.get("AssumeRolePolicyDocument"),
                    "max_session_duration": raw.get("MaxSessionDuration"),
                    "attached_policies": attached,
                }
            )
    except ClientError as exc:
        return build_error_response(
            invocation_id=invocation_id,
            error=handle_client_error(exc),
            started_at=started_at,
            external_api_calls=client.api_calls,
        )

    data = {"roles": roles, "total_count": len(roles)}

    logger.info(
        "tool_invocation_success",
        module="aws",
        action="iam_list_roles",
        tool_name="aws.iam_list_roles",
        total_count=len(roles),
        api_calls=client.api_calls,
    )

    return build_success_response(
        invocation_id=invocation_id,
        data=data,
        started_at=started_at,
        external_api_calls=client.api_calls,
    )
