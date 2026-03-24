"""Shared fixtures for GitHub MCP server tests."""

import pytest

from shared.models import CredentialEnvelope

MOCK_BASE_URL = "https://api.github.com"
MOCK_ORG = "test-org"
MOCK_PAT = "ghp_testtoken1234567890abcdef1234567890"


@pytest.fixture
def github_credentials() -> CredentialEnvelope:
    """A valid GitHub credential envelope for testing."""
    return CredentialEnvelope(
        server_type="github",
        credential_mode="direct",
        credential_data={
            "personal_access_token": MOCK_PAT,
            "organization": MOCK_ORG,
        },
    )


@pytest.fixture
def invocation_id() -> str:
    """A fixed UUID for test invocations."""
    return "550e8400-e29b-41d4-a716-446655440000"


@pytest.fixture
def mock_member_admin() -> dict:
    """A mock GitHub member response (admin)."""
    return {
        "login": "admin-user",
        "id": 1001,
        "site_admin": False,
        "avatar_url": "https://avatars.githubusercontent.com/u/1001",
    }


@pytest.fixture
def mock_member_regular() -> dict:
    """A mock GitHub member response (regular member)."""
    return {
        "login": "regular-user",
        "id": 1002,
        "site_admin": False,
        "avatar_url": "https://avatars.githubusercontent.com/u/1002",
    }


@pytest.fixture
def mock_repo() -> dict:
    """A mock GitHub repository response."""
    return {
        "name": "my-repo",
        "full_name": "test-org/my-repo",
        "visibility": "private",
        "private": True,
        "default_branch": "main",
        "language": "Python",
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-06-01T00:00:00Z",
        "pushed_at": "2025-06-01T12:00:00Z",
        "size": 1024,
        "archived": False,
        "disabled": False,
        "open_issues_count": 5,
    }


@pytest.fixture
def mock_protection_response() -> dict:
    """A mock GitHub branch protection response."""
    return {
        "required_pull_request_reviews": {
            "required_approving_review_count": 2,
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": True,
            "require_last_push_approval": False,
        },
        "required_status_checks": {
            "strict": True,
            "contexts": ["ci/build", "ci/test"],
        },
        "enforce_admins": {"enabled": True},
        "restrictions": {
            "users": [{"login": "deploy-bot"}],
            "teams": [{"slug": "release-team"}],
            "apps": [{"slug": "dependabot"}],
        },
        "required_signatures": {"enabled": False},
        "allow_force_pushes": {"enabled": False},
        "allow_deletions": {"enabled": False},
    }
