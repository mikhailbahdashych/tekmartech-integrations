"""Implements aws.iam_list_users from mcp-tool-interface.yaml.

Lists all IAM users with their metadata, policies, MFA status, and access key
information. Uses boto3 paginators for list_users and optionally enriches each
user with MFA device and access key details.
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
    "tool_name": "aws.iam_list_users",
    "display_name": "List IAM Users",
    "description": (
        "List all IAM users with their metadata, policies, MFA status, and access key information."
    ),
    "category": "identity",
    "input_schema": {
        "type": "object",
        "properties": {
            "path_prefix": {
                "type": "string",
                "description": "Filter users by IAM path prefix. Default '/' (all users).",
                "default": "/",
            },
            "include_mfa": {
                "type": "boolean",
                "description": "Include MFA device info per user. Default true.",
                "default": True,
            },
            "include_access_keys": {
                "type": "boolean",
                "description": "Include access key info per user. Default true.",
                "default": True,
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
                        "username": {"type": "string"},
                        "user_id": {"type": "string"},
                        "arn": {"type": "string"},
                        "path": {"type": "string"},
                        "created_at": {"type": "string", "format": "date-time"},
                        "password_last_used": {
                            "type": "string",
                            "format": "date-time",
                            "nullable": True,
                        },
                        "mfa_devices": {
                            "type": "array",
                            "items": {"type": "object"},
                            "nullable": True,
                        },
                        "access_keys": {
                            "type": "array",
                            "items": {"type": "object"},
                            "nullable": True,
                        },
                    },
                },
            },
            "total_count": {"type": "integer"},
        },
    },
}


async def _list_all_users(client: AWSClient, iam: Any, path_prefix: str) -> list[dict[str, Any]]:
    """Fetch all IAM users using paginator.

    Args:
        client: AWSClient for call counting.
        iam: boto3 IAM client.
        path_prefix: IAM path prefix filter.

    Returns:
        List of raw IAM user dicts.
    """
    paginator = iam.get_paginator("list_users")

    def _paginate() -> list[dict[str, Any]]:
        users: list[dict[str, Any]] = []
        for page in paginator.paginate(PathPrefix=path_prefix):
            client._increment_calls()
            users.extend(page.get("Users", []))
        return users

    return await run_boto3(client, lambda: _paginate())


async def _get_mfa_devices(client: AWSClient, iam: Any, username: str) -> list[dict[str, Any]]:
    """Get MFA devices for a user.

    Args:
        client: AWSClient for call counting.
        iam: boto3 IAM client.
        username: IAM username.

    Returns:
        List of MFA device dicts.
    """
    response = await run_boto3(client, iam.list_mfa_devices, UserName=username)
    return [
        {
            "serial_number": d.get("SerialNumber"),
            "enable_date": d.get("EnableDate", "").isoformat() if d.get("EnableDate") else None,
        }
        for d in response.get("MFADevices", [])
    ]


async def _get_access_keys(client: AWSClient, iam: Any, username: str) -> list[dict[str, Any]]:
    """Get access keys and their last used info for a user.

    Args:
        client: AWSClient for call counting.
        iam: boto3 IAM client.
        username: IAM username.

    Returns:
        List of access key dicts with last_used info.
    """
    response = await run_boto3(client, iam.list_access_keys, UserName=username)
    keys = []
    for key_meta in response.get("AccessKeyMetadata", []):
        key_id = key_meta.get("AccessKeyId", "")
        last_used_resp = await run_boto3(client, iam.get_access_key_last_used, AccessKeyId=key_id)
        last_used_info = last_used_resp.get("AccessKeyLastUsed", {})
        keys.append(
            {
                "access_key_id": key_id,
                "status": key_meta.get("Status"),
                "created_at": key_meta.get("CreateDate", "").isoformat()
                if key_meta.get("CreateDate")
                else None,
                "last_used_at": last_used_info.get("LastUsedDate", "").isoformat()
                if last_used_info.get("LastUsedDate")
                else None,
                "last_used_service": last_used_info.get("ServiceName"),
                "last_used_region": last_used_info.get("Region"),
            }
        )
    return keys


async def execute(
    parameters: dict[str, Any],
    credentials: CredentialEnvelope,
    invocation_id: str,
    timeout_seconds: int = 30,
) -> ToolInvocationResponse:
    """Execute the aws.iam_list_users tool.

    Args:
        parameters: Tool input (path_prefix, include_mfa, include_access_keys).
        credentials: Credential envelope with AWS credentials.
        invocation_id: Unique identifier for this invocation.
        timeout_seconds: Maximum execution time.

    Returns:
        A ToolInvocationResponse with user data or error.
    """
    started_at = datetime.now(UTC)

    logger.debug(
        "tool_invocation_start",
        module="aws",
        action="iam_list_users",
        tool_name="aws.iam_list_users",
    )

    path_prefix = parameters.get("path_prefix", "/")
    include_mfa = parameters.get("include_mfa", True)
    include_access_keys = parameters.get("include_access_keys", True)

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
        raw_users = await _list_all_users(client, iam, path_prefix)
    except ClientError as exc:
        return build_error_response(
            invocation_id=invocation_id,
            error=handle_client_error(exc),
            started_at=started_at,
            external_api_calls=client.api_calls,
        )

    users = []
    try:
        for raw in raw_users:
            username = raw.get("UserName", "")
            user: dict[str, Any] = {
                "username": username,
                "user_id": raw.get("UserId"),
                "arn": raw.get("Arn"),
                "path": raw.get("Path"),
                "created_at": raw.get("CreateDate", "").isoformat()
                if raw.get("CreateDate")
                else None,
                "password_last_used": raw.get("PasswordLastUsed", "").isoformat()
                if raw.get("PasswordLastUsed")
                else None,
                "mfa_devices": None,
                "access_keys": None,
            }
            if include_mfa:
                user["mfa_devices"] = await _get_mfa_devices(client, iam, username)
            if include_access_keys:
                user["access_keys"] = await _get_access_keys(client, iam, username)
            users.append(user)
    except ClientError as exc:
        return build_error_response(
            invocation_id=invocation_id,
            error=handle_client_error(exc),
            started_at=started_at,
            external_api_calls=client.api_calls,
        )

    data = {"users": users, "total_count": len(users)}

    logger.info(
        "tool_invocation_success",
        module="aws",
        action="iam_list_users",
        tool_name="aws.iam_list_users",
        total_count=len(users),
        api_calls=client.api_calls,
    )

    return build_success_response(
        invocation_id=invocation_id,
        data=data,
        started_at=started_at,
        external_api_calls=client.api_calls,
    )
