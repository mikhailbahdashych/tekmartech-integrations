"""Tests for google_workspace.tools.list_user_tokens."""

from unittest.mock import MagicMock, patch

from google_workspace.tools.list_user_tokens import execute


def _mock_gw_client_for_tokens(token_response):
    """Create a mock client returning the given tokens response."""
    mock_client = MagicMock()
    mock_client.api_calls = 0
    mock_client._increment_calls = lambda c=1: setattr(
        mock_client, "api_calls", mock_client.api_calls + c
    )

    mock_directory = MagicMock()
    mock_tokens_resource = MagicMock()
    mock_directory.tokens.return_value = mock_tokens_resource

    mock_list_request = MagicMock()
    mock_list_request.execute = MagicMock(return_value=token_response)
    mock_tokens_resource.list.return_value = mock_list_request

    mock_client.directory_service.return_value = mock_directory
    return mock_client


async def test_list_tokens_success(gw_credentials, invocation_id):
    token_response = {
        "items": [
            {
                "clientId": "client-123.apps.googleusercontent.com",
                "displayText": "My App",
                "scopes": [
                    "https://www.googleapis.com/auth/drive.readonly",
                    "https://www.googleapis.com/auth/calendar.readonly",
                ],
                "nativeApp": False,
                "anonymous": False,
            },
            {
                "clientId": "client-456.apps.googleusercontent.com",
                "displayText": "Another App",
                "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
                "nativeApp": True,
                "anonymous": False,
            },
        ]
    }
    mock_client = _mock_gw_client_for_tokens(token_response)

    with patch("google_workspace.tools.list_user_tokens.GoogleWorkspaceClient") as mock_cls:
        mock_cls.return_value = mock_client
        result = await execute({"user_key": "alice@example.com"}, gw_credentials, invocation_id)

    assert result.status == "success"
    assert result.data["total_count"] == 2

    token = result.data["tokens"][0]
    assert token["client_id"] == "client-123.apps.googleusercontent.com"
    assert token["display_text"] == "My App"
    assert len(token["scopes"]) == 2
    assert token["native_app"] is False
    assert result.metadata.data_hash is not None


async def test_list_tokens_empty(gw_credentials, invocation_id):
    """User with no tokens should return an empty array."""
    mock_client = _mock_gw_client_for_tokens({"items": []})

    with patch("google_workspace.tools.list_user_tokens.GoogleWorkspaceClient") as mock_cls:
        mock_cls.return_value = mock_client
        result = await execute({"user_key": "bob@example.com"}, gw_credentials, invocation_id)

    assert result.status == "success"
    assert result.data["total_count"] == 0
    assert result.data["tokens"] == []


async def test_list_tokens_missing_user_key(gw_credentials, invocation_id):
    result = await execute({}, gw_credentials, invocation_id)

    assert result.status == "error"
    assert result.error.code == "validation.invalid_parameters"
