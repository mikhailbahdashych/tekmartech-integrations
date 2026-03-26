"""Tests for google_workspace.tools.list_login_events."""

from unittest.mock import MagicMock, patch

from google_workspace.tools.list_login_events import execute


def _mock_gw_client_for_reports(pages):
    """Create a mock client with reports service returning activity pages."""
    mock_client = MagicMock()
    mock_client.api_calls = 0
    mock_client._increment_calls = lambda c=1: setattr(
        mock_client, "api_calls", mock_client.api_calls + c
    )

    mock_reports = MagicMock()
    mock_activities_resource = MagicMock()
    mock_reports.activities.return_value = mock_activities_resource

    page_iter = iter(pages)
    mock_list_request = MagicMock()
    mock_list_request.execute = MagicMock(side_effect=lambda: next(page_iter))
    mock_activities_resource.list.return_value = mock_list_request

    mock_client.reports_service.return_value = mock_reports
    return mock_client


MOCK_LOGIN_ACTIVITY = {
    "actor": {"email": "alice@example.com"},
    "ipAddress": "192.168.1.1",
    "id": {"time": "2025-06-01T08:30:00Z"},
    "events": [
        {
            "name": "login_success",
            "parameters": [
                {"name": "login_type", "value": "google_password"},
            ],
        },
    ],
}

MOCK_SUSPICIOUS_ACTIVITY = {
    "actor": {"email": "bob@example.com"},
    "ipAddress": "10.0.0.1",
    "id": {"time": "2025-06-01T09:00:00Z"},
    "events": [
        {
            "name": "suspicious_login",
            "parameters": [
                {"name": "login_type", "value": "exchange"},
            ],
        },
    ],
}


async def test_list_login_events_success(gw_credentials, invocation_id):
    mock_client = _mock_gw_client_for_reports(
        [{"items": [MOCK_LOGIN_ACTIVITY, MOCK_SUSPICIOUS_ACTIVITY]}]
    )

    with patch("google_workspace.tools.list_login_events.GoogleWorkspaceClient") as mock_cls:
        mock_cls.return_value = mock_client
        result = await execute({}, gw_credentials, invocation_id)

    assert result.status == "success"
    assert result.data["total_count"] == 2

    login = result.data["events"][0]
    assert login["actor_email"] == "alice@example.com"
    assert login["event_name"] == "login_success"
    assert login["ip_address"] == "192.168.1.1"
    assert login["login_type"] == "google_password"
    assert login["is_suspicious"] is False

    suspicious = result.data["events"][1]
    assert suspicious["event_name"] == "suspicious_login"
    assert suspicious["is_suspicious"] is True
    assert result.metadata.data_hash is not None


async def test_list_login_events_pagination(gw_credentials, invocation_id):
    page1 = {"items": [MOCK_LOGIN_ACTIVITY], "nextPageToken": "page2-token"}
    page2 = {"items": [MOCK_SUSPICIOUS_ACTIVITY]}
    mock_client = _mock_gw_client_for_reports([page1, page2])

    with patch("google_workspace.tools.list_login_events.GoogleWorkspaceClient") as mock_cls:
        mock_cls.return_value = mock_client
        result = await execute({}, gw_credentials, invocation_id)

    assert result.status == "success"
    assert result.data["total_count"] == 2
    emails = [e["actor_email"] for e in result.data["events"]]
    assert "alice@example.com" in emails
    assert "bob@example.com" in emails


async def test_list_login_events_with_time_range(gw_credentials, invocation_id):
    mock_client = _mock_gw_client_for_reports([{"items": []}])

    with patch("google_workspace.tools.list_login_events.GoogleWorkspaceClient") as mock_cls:
        mock_cls.return_value = mock_client
        result = await execute(
            {
                "start_time": "2025-01-01T00:00:00Z",
                "end_time": "2025-12-31T23:59:59Z",
            },
            gw_credentials,
            invocation_id,
        )

    assert result.status == "success"
    # Verify time range was passed
    mock_reports = mock_client.reports_service.return_value
    call_kwargs = mock_reports.activities.return_value.list.call_args[1]
    assert call_kwargs["startTime"] == "2025-01-01T00:00:00Z"
    assert call_kwargs["endTime"] == "2025-12-31T23:59:59Z"


async def test_list_login_events_with_event_name_filter(gw_credentials, invocation_id):
    mock_client = _mock_gw_client_for_reports([{"items": []}])

    with patch("google_workspace.tools.list_login_events.GoogleWorkspaceClient") as mock_cls:
        mock_cls.return_value = mock_client
        result = await execute({"event_name": "login_failure"}, gw_credentials, invocation_id)

    assert result.status == "success"
    mock_reports = mock_client.reports_service.return_value
    call_kwargs = mock_reports.activities.return_value.list.call_args[1]
    assert call_kwargs["eventName"] == "login_failure"


async def test_list_login_events_empty(gw_credentials, invocation_id):
    mock_client = _mock_gw_client_for_reports([{"items": []}])

    with patch("google_workspace.tools.list_login_events.GoogleWorkspaceClient") as mock_cls:
        mock_cls.return_value = mock_client
        result = await execute({}, gw_credentials, invocation_id)

    assert result.status == "success"
    assert result.data["total_count"] == 0
    assert result.data["events"] == []


async def test_list_login_events_invalid_datetime(gw_credentials, invocation_id):
    result = await execute({"start_time": "not-a-date"}, gw_credentials, invocation_id)

    assert result.status == "error"
    assert result.error.code == "validation.invalid_parameters"


async def test_list_login_events_invalid_max_results(gw_credentials, invocation_id):
    result = await execute({"max_results": 5000}, gw_credentials, invocation_id)

    assert result.status == "error"
    assert result.error.code == "validation.invalid_parameters"
