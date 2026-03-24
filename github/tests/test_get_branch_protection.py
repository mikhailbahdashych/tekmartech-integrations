"""Tests for github.tools.get_branch_protection."""

import httpx
import respx

from github.tests.conftest import MOCK_BASE_URL, MOCK_ORG
from github.tools.get_branch_protection import execute


@respx.mock
async def test_protection_enabled(github_credentials, invocation_id, mock_protection_response):
    respx.get(f"{MOCK_BASE_URL}/repos/{MOCK_ORG}/my-repo/branches/main/protection").mock(
        return_value=httpx.Response(200, json=mock_protection_response)
    )

    result = await execute(
        {"repository": "my-repo", "branch": "main"},
        github_credentials,
        invocation_id,
    )

    assert result.status == "success"
    data = result.data
    assert data["enabled"] is True
    assert data["repository"] == "my-repo"
    assert data["branch"] == "main"
    assert data["required_pull_request_reviews"]["required_approving_review_count"] == 2
    assert data["required_pull_request_reviews"]["dismiss_stale_reviews"] is True
    assert data["required_status_checks"]["strict"] is True
    assert "ci/build" in data["required_status_checks"]["contexts"]
    assert data["enforce_admins"] is True
    assert data["restrictions"]["users"] == ["deploy-bot"]
    assert data["restrictions"]["teams"] == ["release-team"]
    assert data["required_signatures"] is False
    assert data["allow_force_pushes"] is False
    assert data["allow_deletions"] is False
    assert result.metadata.data_hash is not None


@respx.mock
async def test_no_protection_404(github_credentials, invocation_id):
    """A 404 means no protection configured — returned as success with enabled=false."""
    respx.get(f"{MOCK_BASE_URL}/repos/{MOCK_ORG}/my-repo/branches/main/protection").mock(
        return_value=httpx.Response(404, json={"message": "Not Found"})
    )

    result = await execute(
        {"repository": "my-repo", "branch": "main"},
        github_credentials,
        invocation_id,
    )

    assert result.status == "success"
    data = result.data
    assert data["enabled"] is False
    assert data["required_pull_request_reviews"] is None
    assert data["required_status_checks"] is None
    assert data["enforce_admins"] is None
    assert data["restrictions"] is None
    assert data["required_signatures"] is None
    assert data["allow_force_pushes"] is None
    assert data["allow_deletions"] is None


@respx.mock
async def test_default_branch_lookup(github_credentials, invocation_id, mock_protection_response):
    """When branch is omitted, the tool fetches the repo to get default_branch."""
    respx.get(f"{MOCK_BASE_URL}/repos/{MOCK_ORG}/my-repo").mock(
        return_value=httpx.Response(200, json={"default_branch": "develop", "name": "my-repo"})
    )
    respx.get(f"{MOCK_BASE_URL}/repos/{MOCK_ORG}/my-repo/branches/develop/protection").mock(
        return_value=httpx.Response(200, json=mock_protection_response)
    )

    result = await execute(
        {"repository": "my-repo"},
        github_credentials,
        invocation_id,
    )

    assert result.status == "success"
    assert result.data["branch"] == "develop"
    assert result.data["enabled"] is True
    # Should have made 2 API calls (repo lookup + protection)
    assert result.metadata.external_api_calls == 2


@respx.mock
async def test_repo_not_found_404(github_credentials, invocation_id):
    """404 on repo lookup (when finding default branch) IS an error."""
    respx.get(f"{MOCK_BASE_URL}/repos/{MOCK_ORG}/missing-repo").mock(
        return_value=httpx.Response(404, json={"message": "Not Found"})
    )

    result = await execute(
        {"repository": "missing-repo"},
        github_credentials,
        invocation_id,
    )

    assert result.status == "error"
    assert result.error.code == "validation.invalid_parameters"
    assert "not found" in result.error.message.lower()


@respx.mock
async def test_insufficient_permissions_403(github_credentials, invocation_id):
    respx.get(f"{MOCK_BASE_URL}/repos/{MOCK_ORG}/secret-repo/branches/main/protection").mock(
        return_value=httpx.Response(403, json={"message": "Forbidden"})
    )

    result = await execute(
        {"repository": "secret-repo", "branch": "main"},
        github_credentials,
        invocation_id,
    )

    assert result.status == "error"
    assert result.error.code == "auth.insufficient_permissions"
    assert result.error.details.retryable is False


async def test_missing_repository_param(github_credentials, invocation_id):
    result = await execute({}, github_credentials, invocation_id)
    assert result.status == "error"
    assert result.error.code == "validation.invalid_parameters"
