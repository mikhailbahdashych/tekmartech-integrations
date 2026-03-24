#!/usr/bin/env python3
"""Manual test script for the GitHub MCP server against a real GitHub account.

This script is NOT part of the automated test suite. It is a development utility
for manual verification of tool behavior against real GitHub APIs.

Usage:
    export GITHUB_TEST_PAT="ghp_your_token_here"
    export GITHUB_TEST_ORG="your-org-name"
    uv run python scripts/test_github_live.py

Required scopes for classic PATs: repo (read), read:org, admin:org (read-only).
For fine-grained PATs: Organization Members (read), Administration (read),
Repository Contents (read), Metadata (read), Pull requests (read).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

# Ensure the project root is importable
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
    pat = os.environ.get("GITHUB_TEST_PAT")
    org = os.environ.get("GITHUB_TEST_ORG")

    if not pat or not org:
        print("=" * 60)
        print("GitHub Live Test Script")
        print("=" * 60)
        print()
        print("This script tests the GitHub MCP tools against a real")
        print("GitHub organization. Set these environment variables:")
        print()
        print("  export GITHUB_TEST_PAT='ghp_your_token_here'")
        print("  export GITHUB_TEST_ORG='your-org-name'")
        print()
        print("Or copy .env.test.example to .env.test and fill in values,")
        print("then source it: source .env.test")
        print()
        if not pat:
            print("  MISSING: GITHUB_TEST_PAT")
        if not org:
            print("  MISSING: GITHUB_TEST_ORG")
        print()
        return None

    return CredentialEnvelope(
        server_type="github",
        credential_mode="direct",
        credential_data={
            "personal_access_token": pat,
            "organization": org,
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
    """Run all three GitHub tools against the real API."""
    credentials = get_credentials()
    if credentials is None:
        sys.exit(1)

    invocation_id = "live-test-001"
    org = credentials.credential_data["organization"]
    print(f"\nTesting against organization: {org}\n")

    # 1. List organization members
    from github.tools.list_organization_members import execute as exec_members

    print(">>> Testing github.list_organization_members ...")
    result = await exec_members({}, credentials, f"{invocation_id}-members")
    print_result("github.list_organization_members", result)

    # 2. List repositories
    from github.tools.list_repositories import execute as exec_repos

    print("\n>>> Testing github.list_repositories ...")
    result = await exec_repos({}, credentials, f"{invocation_id}-repos")
    print_result("github.list_repositories", result)

    # 3. Get branch protection (use first repo if available)
    if result.status == "success" and result.data["total_count"] > 0:
        repo_name = result.data["repositories"][0]["name"]
        default_branch = result.data["repositories"][0]["default_branch"]

        from github.tools.get_branch_protection import execute as exec_protection

        print(f"\n>>> Testing github.get_branch_protection on {repo_name}/{default_branch} ...")
        result = await exec_protection(
            {"repository": repo_name, "branch": default_branch},
            credentials,
            f"{invocation_id}-protection",
        )
        print_result("github.get_branch_protection", result)
    else:
        print("\nSkipping branch protection test (no repositories found).")

    print("\nDone! All tests completed.")


if __name__ == "__main__":
    asyncio.run(main())
