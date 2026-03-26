#!/usr/bin/env python3
"""Manual test script for the Google Workspace MCP server.

This script is NOT part of the automated test suite. It is a development utility
for manual verification when a Google Workspace test environment is available.

Usage:
    export GOOGLE_TEST_SERVICE_ACCOUNT_JSON='{"type":"service_account",...}'
    # OR: export GOOGLE_TEST_SERVICE_ACCOUNT_JSON=/path/to/key.json
    export GOOGLE_TEST_DELEGATED_EMAIL="admin@your-domain.com"
    uv run python scripts/test_google_workspace_live.py

Setup instructions:
    1. Create a Google Cloud project and enable the Admin SDK API.
    2. Create a service account with domain-wide delegation enabled.
    3. In the Google Workspace Admin console, authorize the service account
       with these scopes:
       - https://www.googleapis.com/auth/admin.directory.user.readonly
       - https://www.googleapis.com/auth/admin.directory.user.security
       - https://www.googleapis.com/auth/admin.reports.audit.readonly
    4. Download the service account key JSON file.
    5. Set the environment variables above.
    6. The delegated_email must be a Workspace super admin account.
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
    sa_json_raw = os.environ.get("GOOGLE_TEST_SERVICE_ACCOUNT_JSON")
    delegated_email = os.environ.get("GOOGLE_TEST_DELEGATED_EMAIL")

    if not sa_json_raw or not delegated_email:
        print("=" * 60)
        print("Google Workspace Live Test Script")
        print("=" * 60)
        print()
        print("This script tests the Google Workspace MCP tools against a real")
        print("Google Workspace domain. Set these environment variables:")
        print()
        print("  export GOOGLE_TEST_SERVICE_ACCOUNT_JSON='{...}'")
        print("    (the full JSON key content, or a file path to the key)")
        print("  export GOOGLE_TEST_DELEGATED_EMAIL='admin@your-domain.com'")
        print()
        print("Setup steps:")
        print("  1. Create a GCP project and enable the Admin SDK API")
        print("  2. Create a service account with domain-wide delegation")
        print("  3. Authorize the service account in Workspace Admin console with:")
        print("     - admin.directory.user.readonly")
        print("     - admin.directory.user.security")
        print("     - admin.reports.audit.readonly")
        print("  4. Download the service account key JSON")
        print("  5. Set the environment variables and run this script")
        print()
        if not sa_json_raw:
            print("  MISSING: GOOGLE_TEST_SERVICE_ACCOUNT_JSON")
        if not delegated_email:
            print("  MISSING: GOOGLE_TEST_DELEGATED_EMAIL")
        print()
        return None

    # Support both inline JSON and file path
    if os.path.isfile(sa_json_raw):
        with open(sa_json_raw) as f:
            sa_json = f.read()
    else:
        sa_json = sa_json_raw

    return CredentialEnvelope(
        server_type="google_workspace",
        credential_mode="direct",
        credential_data={
            "service_account_json": sa_json,
            "delegated_email": delegated_email,
        },
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
    """Run all four Google Workspace tools."""
    credentials = get_credentials()
    if credentials is None:
        sys.exit(1)

    inv = "live-gw-001"
    delegated = credentials.credential_data["delegated_email"]
    print(f"\nTesting with delegated email: {delegated}\n")

    from google_workspace.tools.list_users import execute as exec_users

    print(">>> Testing google_workspace.list_users ...")
    result = await exec_users({}, credentials, f"{inv}-users")
    print_result("google_workspace.list_users", result)

    from google_workspace.tools.get_user_mfa_status import execute as exec_mfa

    print("\n>>> Testing google_workspace.get_user_mfa_status ...")
    result = await exec_mfa({}, credentials, f"{inv}-mfa")
    print_result("google_workspace.get_user_mfa_status", result)

    # Test tokens for the delegated user
    from google_workspace.tools.list_user_tokens import execute as exec_tokens

    print(f"\n>>> Testing google_workspace.list_user_tokens for {delegated} ...")
    result = await exec_tokens({"user_key": delegated}, credentials, f"{inv}-tokens")
    print_result("google_workspace.list_user_tokens", result)

    from google_workspace.tools.list_login_events import execute as exec_login

    print("\n>>> Testing google_workspace.list_login_events ...")
    result = await exec_login({}, credentials, f"{inv}-login")
    print_result("google_workspace.list_login_events", result)

    print("\nDone! All tests completed.")


if __name__ == "__main__":
    asyncio.run(main())
