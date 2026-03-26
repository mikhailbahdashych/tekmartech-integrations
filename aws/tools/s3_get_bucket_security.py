"""Implements aws.s3_get_bucket_security from mcp-tool-interface.yaml.

Retrieves security configuration for a specific S3 bucket: public access block,
bucket policy, encryption settings, versioning status, and logging configuration.
Missing configurations (no policy, no encryption) are handled gracefully as
valid data, not errors.
"""

from __future__ import annotations

import json
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
    "tool_name": "aws.s3_get_bucket_security",
    "display_name": "S3 Bucket Security",
    "description": (
        "Retrieve security configuration for a specific S3 bucket: public access "
        "block, bucket policy, encryption settings, versioning status, and logging "
        "configuration."
    ),
    "category": "configuration",
    "input_schema": {
        "type": "object",
        "properties": {
            "bucket_name": {
                "type": "string",
                "description": "The S3 bucket name to inspect.",
            },
        },
        "required": ["bucket_name"],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "bucket_name": {"type": "string"},
            "public_access_block": {"type": "object", "nullable": True},
            "bucket_policy": {"type": "object", "nullable": True},
            "encryption": {"type": "object", "nullable": True},
            "versioning": {"type": "object"},
            "logging": {"type": "object", "nullable": True},
        },
    },
}

# Error codes that indicate a config is simply absent (not a real error).
_MISSING_CONFIG_CODES = {
    "NoSuchPublicAccessBlockConfiguration",
    "NoSuchBucketPolicy",
    "ServerSideEncryptionConfigurationNotFoundError",
}


async def _get_optional_config(
    client: AWSClient, func: Any, **kwargs: Any
) -> dict[str, Any] | None:
    """Call a boto3 function, returning None if the config doesn't exist.

    Args:
        client: AWSClient for call counting.
        func: boto3 method to call.
        **kwargs: Arguments for the boto3 method.

    Returns:
        The response dict, or None if the config is absent.

    Raises:
        ClientError: For errors other than missing config.
    """
    try:
        return await run_boto3(client, func, **kwargs)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code in _MISSING_CONFIG_CODES:
            return None
        raise


async def execute(
    parameters: dict[str, Any],
    credentials: CredentialEnvelope,
    invocation_id: str,
    timeout_seconds: int = 30,
) -> ToolInvocationResponse:
    """Execute the aws.s3_get_bucket_security tool.

    Args:
        parameters: Tool input (bucket_name).
        credentials: Credential envelope with AWS credentials.
        invocation_id: Unique identifier for this invocation.
        timeout_seconds: Maximum execution time.

    Returns:
        A ToolInvocationResponse with bucket security config or error.
    """
    started_at = datetime.now(UTC)

    logger.debug(
        "tool_invocation_start",
        module="aws",
        action="s3_get_bucket_security",
        tool_name="aws.s3_get_bucket_security",
    )

    bucket_name = parameters.get("bucket_name")
    if not bucket_name or not isinstance(bucket_name, str):
        return build_error_response(
            invocation_id=invocation_id,
            error=format_validation_error(
                "'bucket_name' is required and must be a non-empty string."
            ),
            started_at=started_at,
        )

    aws_creds = extract_aws_credentials(credentials)
    client = AWSClient(aws_creds)
    s3 = client.s3_client()

    try:
        # Public access block
        pab_resp = await _get_optional_config(
            client, s3.get_public_access_block, Bucket=bucket_name
        )
        public_access_block = pab_resp.get("PublicAccessBlockConfiguration") if pab_resp else None

        # Bucket policy
        policy_resp = await _get_optional_config(client, s3.get_bucket_policy, Bucket=bucket_name)
        bucket_policy = None
        if policy_resp:
            try:
                bucket_policy = json.loads(policy_resp.get("Policy", "{}"))
            except (json.JSONDecodeError, TypeError):
                bucket_policy = None

        # Encryption
        enc_resp = await _get_optional_config(client, s3.get_bucket_encryption, Bucket=bucket_name)
        encryption = enc_resp.get("ServerSideEncryptionConfiguration") if enc_resp else None

        # Versioning (always returns a response, Status may be absent)
        ver_resp = await run_boto3(client, s3.get_bucket_versioning, Bucket=bucket_name)
        versioning = {
            "status": ver_resp.get("Status", "Disabled"),
            "mfa_delete": ver_resp.get("MFADelete", "Disabled"),
        }

        # Logging
        log_resp = await run_boto3(client, s3.get_bucket_logging, Bucket=bucket_name)
        logging_config = log_resp.get("LoggingEnabled")

    except ClientError as exc:
        return build_error_response(
            invocation_id=invocation_id,
            error=handle_client_error(exc),
            started_at=started_at,
            external_api_calls=client.api_calls,
        )

    data = {
        "bucket_name": bucket_name,
        "public_access_block": public_access_block,
        "bucket_policy": bucket_policy,
        "encryption": encryption,
        "versioning": versioning,
        "logging": logging_config,
    }

    logger.info(
        "tool_invocation_success",
        module="aws",
        action="s3_get_bucket_security",
        tool_name="aws.s3_get_bucket_security",
        bucket_name=bucket_name,
        api_calls=client.api_calls,
    )

    return build_success_response(
        invocation_id=invocation_id,
        data=data,
        started_at=started_at,
        external_api_calls=client.api_calls,
    )
