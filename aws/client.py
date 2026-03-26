"""boto3 client creation from per-invocation AWS credentials.

Creates a boto3 Session with the provided access key, secret key, optional
session token, and region. Provides methods to get service-specific clients
(IAM, CloudTrail, S3, EC2) and tracks API call counts.

Since boto3 calls are synchronous, all API calls must be wrapped with
asyncio.to_thread() to avoid blocking the MCP server's event loop.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import boto3
import structlog
from botocore.config import Config
from botocore.exceptions import ClientError

from shared.error_formatting import map_boto3_error, sanitize_error_message
from shared.models import AWSCredentials, ToolInvocationError

logger = structlog.get_logger()


class AWSClient:
    """Authenticated boto3 client wrapper for read-only AWS API operations.

    Creates a boto3 session from per-invocation credentials and provides
    service-specific client accessors. Tracks external API call counts
    for metadata reporting.

    Args:
        credentials: AWS credentials (access key, secret key, optional session token, region).
    """

    def __init__(self, credentials: AWSCredentials) -> None:
        max_retries = int(os.environ.get("AWS_MAX_RETRIES", "3"))
        config = Config(retries={"max_attempts": max_retries, "mode": "standard"})

        session_kwargs: dict[str, Any] = {
            "aws_access_key_id": credentials.access_key_id,
            "aws_secret_access_key": credentials.secret_access_key,
            "region_name": credentials.region,
        }
        if credentials.session_token:
            session_kwargs["aws_session_token"] = credentials.session_token

        self._session = boto3.Session(**session_kwargs)
        self._config = config
        self._region = credentials.region
        self._api_calls = 0

    @property
    def region(self) -> str:
        """The AWS region this client operates in."""
        return self._region

    @property
    def api_calls(self) -> int:
        """Total number of external API calls made by this client."""
        return self._api_calls

    def _increment_calls(self, count: int = 1) -> None:
        """Increment the API call counter."""
        self._api_calls += count

    def iam_client(self) -> Any:
        """Create an IAM service client."""
        return self._session.client("iam", config=self._config)

    def cloudtrail_client(self) -> Any:
        """Create a CloudTrail service client."""
        return self._session.client("cloudtrail", config=self._config)

    def s3_client(self) -> Any:
        """Create an S3 service client."""
        return self._session.client("s3", config=self._config)

    def ec2_client(self) -> Any:
        """Create an EC2 service client."""
        return self._session.client("ec2", config=self._config)


# Set to False in tests to skip asyncio.to_thread (moto mocks are thread-local).
_use_thread: bool = True


async def run_boto3(client: AWSClient, func: Any, *args: Any, **kwargs: Any) -> Any:
    """Run a synchronous boto3 call, optionally in a thread.

    In production, uses asyncio.to_thread to avoid blocking the event loop.
    In tests, calls directly (moto mocks are thread-local).

    Args:
        client: The AWSClient instance (for call counting).
        func: The boto3 method to call (e.g. iam.list_users).
        *args: Positional arguments for the boto3 method.
        **kwargs: Keyword arguments for the boto3 method.

    Returns:
        The boto3 response dict.

    Raises:
        botocore.exceptions.ClientError: On AWS API errors.
    """
    client._increment_calls()
    logger.debug(
        "aws_api_call",
        module="aws",
        action="api_call",
        method=getattr(func, "__name__", str(func)),
        api_call_number=client.api_calls,
    )
    if _use_thread:
        return await asyncio.to_thread(func, *args, **kwargs)
    return func(*args, **kwargs)


def handle_client_error(exc: ClientError) -> ToolInvocationError:
    """Map a boto3 ClientError to a contract ToolInvocationError.

    Args:
        exc: The boto3 ClientError exception.

    Returns:
        A ToolInvocationError with the appropriate error code.
    """
    error_code = exc.response.get("Error", {}).get("Code", "Unknown")
    error_message = exc.response.get("Error", {}).get("Message", str(exc))
    return map_boto3_error(error_code, sanitize_error_message(error_message))
