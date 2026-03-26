"""Tests for google_workspace.tools.get_user_mfa_status."""

from unittest.mock import MagicMock, patch

from google_workspace.tools.get_user_mfa_status import execute


def _mock_gw_client_for_mfa(*, single_user=None, user_list_pages=None):
    """Create a mock client for MFA status queries."""
    mock_client = MagicMock()
    mock_client.api_calls = 0
    mock_client._increment_calls = lambda c=1: setattr(
        mock_client, "api_calls", mock_client.api_calls + c
    )

    mock_directory = MagicMock()
    mock_users_resource = MagicMock()
    mock_directory.users.return_value = mock_users_resource

    if single_user is not None:
        mock_get_request = MagicMock()
        mock_get_request.execute = MagicMock(return_value=single_user)
        mock_users_resource.get.return_value = mock_get_request

    if user_list_pages is not None:
        page_iter = iter(user_list_pages)
        mock_list_request = MagicMock()
        mock_list_request.execute = MagicMock(side_effect=lambda: next(page_iter))
        mock_users_resource.list.return_value = mock_list_request

    mock_client.directory_service.return_value = mock_directory
    return mock_client


async def test_mfa_status_single_user(gw_credentials, invocation_id):
    user = {
        "primaryEmail": "alice@example.com",
        "isEnrolledIn2Sv": True,
        "isEnforcedIn2Sv": True,
        "lastLoginTime": "2025-06-01T08:30:00Z",
    }
    mock_client = _mock_gw_client_for_mfa(single_user=user)

    with patch("google_workspace.tools.get_user_mfa_status.GoogleWorkspaceClient") as mock_cls:
        mock_cls.return_value = mock_client
        result = await execute({"user_key": "alice@example.com"}, gw_credentials, invocation_id)

    assert result.status == "success"
    assert result.data["total_count"] == 1
    status = result.data["mfa_statuses"][0]
    assert status["primary_email"] == "alice@example.com"
    assert status["is_enrolled_in_2sv"] is True
    assert status["is_enforced_in_2sv"] is True


async def test_mfa_status_all_users(gw_credentials, invocation_id):
    users_page = {
        "users": [
            {
                "primaryEmail": "alice@example.com",
                "isEnrolledIn2Sv": True,
                "isEnforcedIn2Sv": True,
                "lastLoginTime": "2025-06-01T08:30:00Z",
            },
            {
                "primaryEmail": "bob@example.com",
                "isEnrolledIn2Sv": False,
                "isEnforcedIn2Sv": False,
                "lastLoginTime": None,
            },
        ]
    }
    mock_client = _mock_gw_client_for_mfa(user_list_pages=[users_page])

    with patch("google_workspace.tools.get_user_mfa_status.GoogleWorkspaceClient") as mock_cls:
        mock_cls.return_value = mock_client
        result = await execute({}, gw_credentials, invocation_id)

    assert result.status == "success"
    assert result.data["total_count"] == 2

    enrolled = [s for s in result.data["mfa_statuses"] if s["is_enrolled_in_2sv"]]
    assert len(enrolled) == 1
    assert enrolled[0]["primary_email"] == "alice@example.com"
    assert result.metadata.data_hash is not None
