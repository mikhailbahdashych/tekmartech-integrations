"""Tests for google_workspace.tools.list_users."""

from unittest.mock import MagicMock, patch

from google_workspace.tools.list_users import execute


def _mock_gw_client(pages):
    """Create a mock GoogleWorkspaceClient with directory service returning pages.

    Args:
        pages: List of response dicts, one per page. Each should have 'users'
               and optionally 'nextPageToken'.
    """
    mock_client = MagicMock()
    mock_client.api_calls = 0
    mock_client._increment_calls = lambda c=1: setattr(
        mock_client, "api_calls", mock_client.api_calls + c
    )

    # Chain: directory.users().list(**kwargs).execute() returns page responses
    mock_directory = MagicMock()
    mock_users_resource = MagicMock()
    mock_directory.users.return_value = mock_users_resource

    page_iter = iter(pages)
    mock_list_request = MagicMock()
    mock_list_request.execute = MagicMock(side_effect=lambda: next(page_iter))
    mock_users_resource.list.return_value = mock_list_request

    mock_client.directory_service.return_value = mock_directory
    return mock_client


MOCK_USER_1 = {
    "primaryEmail": "alice@example.com",
    "name": {"fullName": "Alice Smith"},
    "orgUnitPath": "/Engineering",
    "isAdmin": True,
    "isDelegatedAdmin": False,
    "suspended": False,
    "archived": False,
    "creationTime": "2024-01-15T10:00:00Z",
    "lastLoginTime": "2025-06-01T08:30:00Z",
    "isEnrolledIn2Sv": True,
    "isEnforcedIn2Sv": True,
}

MOCK_USER_2 = {
    "primaryEmail": "bob@example.com",
    "name": {"fullName": "Bob Jones"},
    "orgUnitPath": "/Sales",
    "isAdmin": False,
    "isDelegatedAdmin": False,
    "suspended": False,
    "archived": False,
    "creationTime": "2024-03-01T12:00:00Z",
    "lastLoginTime": None,
    "isEnrolledIn2Sv": False,
    "isEnforcedIn2Sv": False,
}


async def test_list_users_success(gw_credentials, invocation_id):
    mock_client = _mock_gw_client([{"users": [MOCK_USER_1, MOCK_USER_2]}])

    with patch("google_workspace.tools.list_users.GoogleWorkspaceClient") as mock_cls:
        mock_cls.return_value = mock_client
        result = await execute({}, gw_credentials, invocation_id)

    assert result.status == "success"
    assert result.data["total_count"] == 2

    alice = result.data["users"][0]
    assert alice["primary_email"] == "alice@example.com"
    assert alice["full_name"] == "Alice Smith"
    assert alice["org_unit_path"] == "/Engineering"
    assert alice["is_admin"] is True
    assert alice["is_enrolled_in_2sv"] is True

    bob = result.data["users"][1]
    assert bob["primary_email"] == "bob@example.com"
    assert bob["is_enrolled_in_2sv"] is False
    assert result.metadata.data_hash is not None


async def test_list_users_pagination(gw_credentials, invocation_id):
    page1 = {"users": [MOCK_USER_1], "nextPageToken": "token-page2"}
    page2 = {"users": [MOCK_USER_2]}
    mock_client = _mock_gw_client([page1, page2])

    with patch("google_workspace.tools.list_users.GoogleWorkspaceClient") as mock_cls:
        mock_cls.return_value = mock_client
        result = await execute({}, gw_credentials, invocation_id)

    assert result.status == "success"
    assert result.data["total_count"] == 2
    emails = [u["primary_email"] for u in result.data["users"]]
    assert "alice@example.com" in emails
    assert "bob@example.com" in emails


async def test_list_users_with_query(gw_credentials, invocation_id):
    mock_client = _mock_gw_client([{"users": [MOCK_USER_1]}])

    with patch("google_workspace.tools.list_users.GoogleWorkspaceClient") as mock_cls:
        mock_cls.return_value = mock_client
        result = await execute({"query": "orgUnitPath=/Engineering"}, gw_credentials, invocation_id)

    assert result.status == "success"
    assert result.data["total_count"] == 1
    # Verify query was passed to the API call
    mock_directory = mock_client.directory_service.return_value
    call_kwargs = mock_directory.users.return_value.list.call_args[1]
    assert call_kwargs["query"] == "orgUnitPath=/Engineering"


async def test_list_users_empty(gw_credentials, invocation_id):
    mock_client = _mock_gw_client([{"users": []}])

    with patch("google_workspace.tools.list_users.GoogleWorkspaceClient") as mock_cls:
        mock_cls.return_value = mock_client
        result = await execute({}, gw_credentials, invocation_id)

    assert result.status == "success"
    assert result.data["total_count"] == 0
    assert result.data["users"] == []
