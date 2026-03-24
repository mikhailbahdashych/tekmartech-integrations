"""Tests for github.tools.list_repositories."""

import httpx
import respx

from github.tests.conftest import MOCK_BASE_URL, MOCK_ORG
from github.tools.list_repositories import execute


@respx.mock
async def test_list_repos_success(github_credentials, invocation_id, mock_repo):
    respx.get(f"{MOCK_BASE_URL}/orgs/{MOCK_ORG}/repos").mock(
        return_value=httpx.Response(200, json=[mock_repo])
    )
    result = await execute({}, github_credentials, invocation_id)

    assert result.status == "success"
    assert result.data is not None
    repos = result.data["repositories"]
    assert len(repos) == 1
    assert repos[0]["name"] == "my-repo"
    assert repos[0]["full_name"] == "test-org/my-repo"
    assert repos[0]["visibility"] == "private"
    assert repos[0]["private"] is True
    assert repos[0]["language"] == "Python"
    assert result.data["total_count"] == 1
    assert result.metadata.data_hash is not None
    assert result.metadata.external_api_calls >= 1


@respx.mock
async def test_list_repos_with_type_filter(github_credentials, invocation_id, mock_repo):
    route = respx.get(f"{MOCK_BASE_URL}/orgs/{MOCK_ORG}/repos").mock(
        return_value=httpx.Response(200, json=[mock_repo])
    )
    result = await execute({"type": "private"}, github_credentials, invocation_id)

    assert result.status == "success"
    # Verify the type param was passed in the request
    assert route.called
    request = route.calls[0].request
    assert "type=private" in str(request.url)


@respx.mock
async def test_list_repos_pagination(github_credentials, invocation_id):
    repo1 = {
        "name": "repo-1",
        "full_name": "test-org/repo-1",
        "visibility": "public",
        "private": False,
        "default_branch": "main",
        "language": "Go",
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
        "pushed_at": None,
        "size": 100,
        "archived": False,
        "disabled": False,
        "open_issues_count": 0,
    }
    repo2 = {
        "name": "repo-2",
        "full_name": "test-org/repo-2",
        "visibility": "private",
        "private": True,
        "default_branch": "develop",
        "language": "Rust",
        "created_at": "2025-02-01T00:00:00Z",
        "updated_at": "2025-02-01T00:00:00Z",
        "pushed_at": "2025-02-15T00:00:00Z",
        "size": 200,
        "archived": False,
        "disabled": False,
        "open_issues_count": 3,
    }

    page2_url = f"{MOCK_BASE_URL}/orgs/{MOCK_ORG}/repos?page=2&per_page=100&type=all&sort=created"

    # Use side_effect to return different responses on successive calls
    responses = iter(
        [
            httpx.Response(
                200,
                json=[repo1],
                headers={"Link": f'<{page2_url}>; rel="next"'},
            ),
            httpx.Response(200, json=[repo2]),
        ]
    )
    respx.get(f"{MOCK_BASE_URL}/orgs/{MOCK_ORG}/repos").mock(
        side_effect=lambda req: next(responses)
    )
    # Also mock the absolute page 2 URL
    respx.get(page2_url).mock(return_value=httpx.Response(200, json=[repo2]))

    result = await execute({}, github_credentials, invocation_id)
    assert result.status == "success"
    assert result.data["total_count"] == 2
    names = [r["name"] for r in result.data["repositories"]]
    assert names == ["repo-1", "repo-2"]


@respx.mock
async def test_list_repos_empty_org(github_credentials, invocation_id):
    respx.get(f"{MOCK_BASE_URL}/orgs/{MOCK_ORG}/repos").mock(
        return_value=httpx.Response(200, json=[])
    )
    result = await execute({}, github_credentials, invocation_id)
    assert result.status == "success"
    assert result.data["repositories"] == []
    assert result.data["total_count"] == 0


@respx.mock
async def test_list_repos_auth_error_401(github_credentials, invocation_id):
    respx.get(f"{MOCK_BASE_URL}/orgs/{MOCK_ORG}/repos").mock(
        return_value=httpx.Response(401, json={"message": "Bad credentials"})
    )
    result = await execute({}, github_credentials, invocation_id)
    assert result.status == "error"
    assert result.error.code == "auth.invalid_credentials"
    assert result.error.details.retryable is False


@respx.mock
async def test_list_repos_server_error_500(github_credentials, invocation_id):
    respx.get(f"{MOCK_BASE_URL}/orgs/{MOCK_ORG}/repos").mock(
        return_value=httpx.Response(500, json={"message": "Internal server error"})
    )
    result = await execute({}, github_credentials, invocation_id)
    assert result.status == "error"
    assert result.error.code == "external.api_error"
    assert result.error.details.retryable is True


async def test_list_repos_invalid_type(github_credentials, invocation_id):
    result = await execute({"type": "invalid"}, github_credentials, invocation_id)
    assert result.status == "error"
    assert result.error.code == "validation.invalid_parameters"
