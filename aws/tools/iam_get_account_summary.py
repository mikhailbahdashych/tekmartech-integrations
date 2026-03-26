"""Implements aws.iam_get_account_summary from mcp-tool-interface.yaml.

Retrieves IAM account-level summary including counts of users, roles,
policies, and MFA device usage. Single non-paginated call.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from botocore.exceptions import ClientError

from aws.client import AWSClient, handle_client_error, run_boto3
from shared.credential_handler import extract_aws_credentials
from shared.models import CredentialEnvelope, ToolInvocationResponse
from shared.response_builder import build_error_response, build_success_response

logger = structlog.get_logger()

definition: dict[str, Any] = {
    "tool_name": "aws.iam_get_account_summary",
    "display_name": "IAM Account Summary",
    "description": (
        "Retrieve IAM account-level summary including counts of users, roles, "
        "policies, and MFA device usage."
    ),
    "category": "identity",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "summary_map": {
                "type": "object",
                "description": "IAM account summary counts keyed by metric name.",
            },
        },
    },
}


async def execute(
    parameters: dict[str, Any],
    credentials: CredentialEnvelope,
    invocation_id: str,
    timeout_seconds: int = 30,
) -> ToolInvocationResponse:
    """Execute the aws.iam_get_account_summary tool.

    Args:
        parameters: No parameters for this tool.
        credentials: Credential envelope with AWS access key and region.
        invocation_id: Unique identifier for this invocation.
        timeout_seconds: Maximum execution time.

    Returns:
        A ToolInvocationResponse with the IAM account summary map.
    """
    started_at = datetime.now(UTC)

    logger.debug(
        "tool_invocation_start",
        module="aws",
        action="iam_get_account_summary",
        tool_name="aws.iam_get_account_summary",
    )

    aws_creds = extract_aws_credentials(credentials)
    client = AWSClient(aws_creds)
    iam = client.iam_client()

    try:
        response = await run_boto3(client, iam.get_account_summary)
    except ClientError as exc:
        return build_error_response(
            invocation_id=invocation_id,
            error=handle_client_error(exc),
            started_at=started_at,
            external_api_calls=client.api_calls,
        )

    data = {"summary_map": response.get("SummaryMap", {})}

    logger.info(
        "tool_invocation_success",
        module="aws",
        action="iam_get_account_summary",
        tool_name="aws.iam_get_account_summary",
        api_calls=client.api_calls,
    )

    return build_success_response(
        invocation_id=invocation_id,
        data=data,
        started_at=started_at,
        external_api_calls=client.api_calls,
    )
