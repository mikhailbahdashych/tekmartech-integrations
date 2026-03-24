"""Tests for github.tools.list_organization_members."""

import httpx
import respx

from github.tests.conftest import MOCK_BASE_URL, MOCK_ORG, MOCK_PAT
from github.tools.list_organization_members import execute


@respx.mock
async def test_list_all_members_success(
    github_credentials, invocation_id, mock_member_admin, mock_member_regular
):
    members_url = f"{MOCK_BASE_URL}/orgs/{MOCK_ORG}/members"

    # Admin list
    respx.get(members_url, params__contains={"role": "admin"}).mock(
        return_value=httpx.Response(200, json=[mock_member_admin])
    )
    # Member list
    respx.get(members_url, params__contains={"role": "member"}).mock(
        return_value=httpx.Response(200, json=[mock_member_regular])
    )
    # 2FA disabled list (empty = everyone has 2FA)
    respx.get(members_url, params__contains={"filter": "2fa_disabled"}).mock(
        return_value=httpx.Response(200, json=[])
    )

    result = await execute({}, github_credentials, invocation_id)

    assert result.status == "success"
    members = result.data["members"]
    assert result.data["total_count"] == 2

    admin = next(m for m in members if m["login"] == "admin-user")
    assert admin["role"] == "admin"
    assert admin["two_factor_enabled"] is True
    assert admin["id"] == 1001

    member = next(m for m in members if m["login"] == "regular-user")
    assert member["role"] == "member"
    assert member["two_factor_enabled"] is True

    assert result.metadata.data_hash is not None
    assert result.metadata.external_api_calls >= 3


@respx.mock
async def test_list_admin_only(github_credentials, invocation_id, mock_member_admin):
    members_url = f"{MOCK_BASE_URL}/orgs/{MOCK_ORG}/members"

    respx.get(members_url, params__contains={"role": "admin"}).mock(
        return_value=httpx.Response(200, json=[mock_member_admin])
    )
    respx.get(members_url, params__contains={"filter": "2fa_disabled"}).mock(
        return_value=httpx.Response(200, json=[])
    )

    result = await execute({"role": "admin"}, github_credentials, invocation_id)

    assert result.status == "success"
    assert result.data["total_count"] == 1
    assert result.data["members"][0]["role"] == "admin"


@respx.mock
async def test_pagination_multiple_pages(github_credentials, invocation_id):
    members_url = f"{MOCK_BASE_URL}/orgs/{MOCK_ORG}/members"
    page2_url = f"{members_url}?role=admin&per_page=100&page=2"

    member1 = {"login": "user1", "id": 1, "site_admin": False, "avatar_url": ""}
    member2 = {"login": "user2", "id": 2, "site_admin": False, "avatar_url": ""}

    # Admin list: page 1 returns Link header, page 2 returns no Link header.
    # Use side_effect to return different responses on successive calls.
    admin_responses = iter(
        [
            httpx.Response(
                200,
                json=[member1],
                headers={"Link": f'<{page2_url}>; rel="next"'},
            ),
            httpx.Response(200, json=[member2]),
        ]
    )
    respx.get(members_url, params__contains={"role": "admin"}).mock(
        side_effect=lambda req: next(admin_responses)
    )
    # The page 2 absolute URL also needs a route (httpx sends it as absolute)
    respx.get(page2_url).mock(return_value=httpx.Response(200, json=[member2]))
    # Empty member list
    respx.get(members_url, params__contains={"role": "member"}).mock(
        return_value=httpx.Response(200, json=[])
    )
    # 2FA disabled
    respx.get(members_url, params__contains={"filter": "2fa_disabled"}).mock(
        return_value=httpx.Response(200, json=[])
    )

    result = await execute({}, github_credentials, invocation_id)

    assert result.status == "success"
    assert result.data["total_count"] == 2
    logins = [m["login"] for m in result.data["members"]]
    assert "user1" in logins
    assert "user2" in logins


@respx.mock
async def test_2fa_disabled_member(
    github_credentials, invocation_id, mock_member_admin, mock_member_regular
):
    members_url = f"{MOCK_BASE_URL}/orgs/{MOCK_ORG}/members"

    respx.get(members_url, params__contains={"role": "admin"}).mock(
        return_value=httpx.Response(200, json=[mock_member_admin])
    )
    respx.get(members_url, params__contains={"role": "member"}).mock(
        return_value=httpx.Response(200, json=[mock_member_regular])
    )
    # regular-user has 2FA disabled
    respx.get(members_url, params__contains={"filter": "2fa_disabled"}).mock(
        return_value=httpx.Response(200, json=[{"login": "regular-user", "id": 1002}])
    )

    result = await execute({}, github_credentials, invocation_id)

    assert result.status == "success"
    admin = next(m for m in result.data["members"] if m["login"] == "admin-user")
    assert admin["two_factor_enabled"] is True

    member = next(m for m in result.data["members"] if m["login"] == "regular-user")
    assert member["two_factor_enabled"] is False


@respx.mock
async def test_2fa_filter_forbidden_graceful_degradation(
    github_credentials, invocation_id, mock_member_admin
):
    """When 2FA filter returns 403 (non-owner), degrade gracefully."""
    members_url = f"{MOCK_BASE_URL}/orgs/{MOCK_ORG}/members"

    respx.get(members_url, params__contains={"role": "admin"}).mock(
        return_value=httpx.Response(200, json=[mock_member_admin])
    )
    respx.get(members_url, params__contains={"role": "member"}).mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get(members_url, params__contains={"filter": "2fa_disabled"}).mock(
        return_value=httpx.Response(403, json={"message": "Must be an owner"})
    )

    result = await execute({}, github_credentials, invocation_id)

    assert result.status == "success"
    assert result.data["total_count"] == 1
    # two_factor_enabled should be null (unknown) when 2FA check is forbidden
    assert result.data["members"][0]["two_factor_enabled"] is None


@respx.mock
async def test_auth_error_401(github_credentials, invocation_id):
    members_url = f"{MOCK_BASE_URL}/orgs/{MOCK_ORG}/members"
    respx.get(members_url, params__contains={"role": "admin"}).mock(
        return_value=httpx.Response(401, json={"message": "Bad credentials"})
    )

    result = await execute({}, github_credentials, invocation_id)

    assert result.status == "error"
    assert result.error.code == "auth.invalid_credentials"
    assert result.error.details.retryable is False


async def test_invalid_role_parameter(github_credentials, invocation_id):
    result = await execute({"role": "superadmin"}, github_credentials, invocation_id)
    assert result.status == "error"
    assert result.error.code == "validation.invalid_parameters"


@respx.mock
async def test_credentials_not_in_error_message(github_credentials, invocation_id):
    """Verify that the PAT does not appear in any error messages."""
    members_url = f"{MOCK_BASE_URL}/orgs/{MOCK_ORG}/members"
    respx.get(members_url, params__contains={"role": "admin"}).mock(
        return_value=httpx.Response(401, json={"message": f"Bad credentials for token {MOCK_PAT}"})
    )

    result = await execute({}, github_credentials, invocation_id)

    assert result.status == "error"
    # The PAT should not appear anywhere in the response
    response_json = result.model_dump_json()
    assert MOCK_PAT not in response_json
