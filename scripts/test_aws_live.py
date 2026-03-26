#!/usr/bin/env python3
"""Manual test script for the AWS MCP server against a real AWS account.

This script is NOT part of the automated test suite. It is a development utility
for manual verification of tool behavior against real AWS APIs.

Usage:
    export AWS_TEST_ACCESS_KEY_ID="AKIA..."
    export AWS_TEST_SECRET_ACCESS_KEY="..."
    export AWS_TEST_REGION="us-east-1"
    uv run python scripts/test_aws_live.py

Required IAM permissions: ReadOnlyAccess or equivalent.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import structlog

from shared.models import CredentialEnvelope

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
)


def get_credentials() -> CredentialEnvelope | None:
    """Read test credentials from environment variables."""
    key_id = os.environ.get("AWS_TEST_ACCESS_KEY_ID")
    secret = os.environ.get("AWS_TEST_SECRET_ACCESS_KEY")
    region = os.environ.get("AWS_TEST_REGION", "us-east-1")

    if not key_id or not secret:
        print("=" * 60)
        print("AWS Live Test Script")
        print("=" * 60)
        print()
        print("This script tests the AWS MCP tools against a real AWS account.")
        print("Set these environment variables:")
        print()
        print("  export AWS_TEST_ACCESS_KEY_ID='AKIA...'")
        print("  export AWS_TEST_SECRET_ACCESS_KEY='...'")
        print("  export AWS_TEST_REGION='us-east-1'  (optional)")
        print()
        if not key_id:
            print("  MISSING: AWS_TEST_ACCESS_KEY_ID")
        if not secret:
            print("  MISSING: AWS_TEST_SECRET_ACCESS_KEY")
        print()
        return None

    cred_data = {
        "access_key_id": key_id,
        "secret_access_key": secret,
        "region": region,
    }
    session_token = os.environ.get("AWS_TEST_SESSION_TOKEN")
    if session_token:
        cred_data["session_token"] = session_token

    return CredentialEnvelope(
        server_type="aws",
        credential_mode="direct",
        credential_data=cred_data,
    )


def print_result(tool_name: str, result) -> None:
    """Pretty-print a tool invocation result."""
    print(f"\n{'=' * 60}")
    print(f"Tool: {tool_name}")
    print(f"Status: {result.status}")
    print(f"API calls: {result.metadata.external_api_calls}")
    print(f"Duration: {result.metadata.duration_ms}ms")
    if result.data:
        print(f"Data hash: {result.metadata.data_hash}")
        print(f"Data:\n{json.dumps(result.data, indent=2, default=str)[:2000]}")
    if result.error:
        print(f"Error: {result.error.code} - {result.error.message}")
    print("=" * 60)


async def main() -> None:
    """Run all seven AWS tools against the real API."""
    credentials = get_credentials()
    if credentials is None:
        sys.exit(1)

    inv = "live-aws-001"
    region = credentials.credential_data["region"]
    print(f"\nTesting against AWS region: {region}\n")

    from aws.tools.iam_get_account_summary import execute as exec_summary

    print(">>> Testing aws.iam_get_account_summary ...")
    result = await exec_summary({}, credentials, f"{inv}-summary")
    print_result("aws.iam_get_account_summary", result)

    from aws.tools.iam_list_users import execute as exec_users

    print("\n>>> Testing aws.iam_list_users ...")
    result = await exec_users({}, credentials, f"{inv}-users")
    print_result("aws.iam_list_users", result)

    from aws.tools.iam_list_roles import execute as exec_roles

    print("\n>>> Testing aws.iam_list_roles ...")
    result = await exec_roles({}, credentials, f"{inv}-roles")
    print_result("aws.iam_list_roles", result)

    from aws.tools.cloudtrail_lookup_events import execute as exec_ct

    print("\n>>> Testing aws.cloudtrail_lookup_events ...")
    result = await exec_ct({}, credentials, f"{inv}-cloudtrail")
    print_result("aws.cloudtrail_lookup_events", result)

    from aws.tools.s3_list_buckets import execute as exec_buckets

    print("\n>>> Testing aws.s3_list_buckets ...")
    result = await exec_buckets({}, credentials, f"{inv}-buckets")
    print_result("aws.s3_list_buckets", result)

    if result.status == "success" and result.data["total_count"] > 0:
        bucket_name = result.data["buckets"][0]["name"]

        from aws.tools.s3_get_bucket_security import execute as exec_security

        print(f"\n>>> Testing aws.s3_get_bucket_security on {bucket_name} ...")
        result = await exec_security({"bucket_name": bucket_name}, credentials, f"{inv}-security")
        print_result("aws.s3_get_bucket_security", result)
    else:
        print("\nSkipping s3_get_bucket_security (no buckets found).")

    from aws.tools.ec2_describe_security_groups import execute as exec_sg

    print("\n>>> Testing aws.ec2_describe_security_groups ...")
    result = await exec_sg({}, credentials, f"{inv}-sg")
    print_result("aws.ec2_describe_security_groups", result)

    print("\nDone! All tests completed.")


if __name__ == "__main__":
    asyncio.run(main())
