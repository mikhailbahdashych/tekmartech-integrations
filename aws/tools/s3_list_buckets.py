"""Implements aws.s3_list_buckets from mcp-tool-interface.yaml.

Lists all S3 buckets with their creation dates and regions. Not paginated
(AWS returns all buckets in one call). For each bucket, calls
get_bucket_location to determine the region.
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
    "tool_name": "aws.s3_list_buckets",
    "display_name": "List S3 Buckets",
    "description": "List all S3 buckets with their creation dates and regions.",
    "category": "storage",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "buckets": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "creation_date": {"type": "string", "format": "date-time"},
                        "region": {"type": "string"},
                    },
                },
            },
            "total_count": {"type": "integer"},
        },
    },
}


async def execute(
    parameters: dict[str, Any],
    credentials: CredentialEnvelope,
    invocation_id: str,
    timeout_seconds: int = 30,
) -> ToolInvocationResponse:
    """Execute the aws.s3_list_buckets tool.

    Args:
        parameters: No parameters for this tool.
        credentials: Credential envelope with AWS credentials.
        invocation_id: Unique identifier for this invocation.
        timeout_seconds: Maximum execution time.

    Returns:
        A ToolInvocationResponse with bucket data or error.
    """
    started_at = datetime.now(UTC)

    logger.debug(
        "tool_invocation_start",
        module="aws",
        action="s3_list_buckets",
        tool_name="aws.s3_list_buckets",
    )

    aws_creds = extract_aws_credentials(credentials)
    client = AWSClient(aws_creds)
    s3 = client.s3_client()

    try:
        response = await run_boto3(client, s3.list_buckets)
    except ClientError as exc:
        return build_error_response(
            invocation_id=invocation_id,
            error=handle_client_error(exc),
            started_at=started_at,
            external_api_calls=client.api_calls,
        )

    buckets = []
    try:
        for bucket in response.get("Buckets", []):
            bucket_name = bucket.get("Name", "")
            # get_bucket_location: None means us-east-1
            loc_resp = await run_boto3(client, s3.get_bucket_location, Bucket=bucket_name)
            region = loc_resp.get("LocationConstraint") or "us-east-1"

            buckets.append(
                {
                    "name": bucket_name,
                    "creation_date": bucket.get("CreationDate", "").isoformat()
                    if bucket.get("CreationDate")
                    else None,
                    "region": region,
                }
            )
    except ClientError as exc:
        return build_error_response(
            invocation_id=invocation_id,
            error=handle_client_error(exc),
            started_at=started_at,
            external_api_calls=client.api_calls,
        )

    data = {"buckets": buckets, "total_count": len(buckets)}

    logger.info(
        "tool_invocation_success",
        module="aws",
        action="s3_list_buckets",
        tool_name="aws.s3_list_buckets",
        total_count=len(buckets),
        api_calls=client.api_calls,
    )

    return build_success_response(
        invocation_id=invocation_id,
        data=data,
        started_at=started_at,
        external_api_calls=client.api_calls,
    )
