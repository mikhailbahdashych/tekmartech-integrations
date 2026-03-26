"""Tests for aws.tools.cloudtrail_lookup_events.

Note: moto does not implement CloudTrail lookup_events, so we mock the
boto3 client directly using unittest.mock.
"""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from aws.tools.cloudtrail_lookup_events import execute


def _mock_cloudtrail_client(events=None):
    """Create a mock CloudTrail client returning the given events."""
    mock_ct = MagicMock()
    mock_ct.lookup_events.return_value = {
        "Events": events or [],
    }
    return mock_ct


async def test_lookup_events_default_params(aws_credentials, invocation_id):
    """Default call with no filters should return success."""
    mock_event = {
        "EventId": "evt-123",
        "EventTime": datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC),
        "EventName": "ConsoleLogin",
        "EventSource": "signin.amazonaws.com",
        "Username": "testuser",
        "Resources": [],
        "CloudTrailEvent": json.dumps({"eventVersion": "1.08", "eventName": "ConsoleLogin"}),
    }
    mock_ct = _mock_cloudtrail_client([mock_event])

    with patch("aws.tools.cloudtrail_lookup_events.AWSClient") as mock_cls:
        mock_client = MagicMock()
        mock_client.cloudtrail_client.return_value = mock_ct
        mock_client.api_calls = 0
        mock_client._increment_calls = lambda c=1: setattr(
            mock_client, "api_calls", mock_client.api_calls + c
        )
        mock_cls.return_value = mock_client

        result = await execute({}, aws_credentials, invocation_id)

    assert result.status == "success"
    assert result.data["total_count"] == 1
    event = result.data["events"][0]
    assert event["event_id"] == "evt-123"
    assert event["event_name"] == "ConsoleLogin"
    assert event["username"] == "testuser"
    assert event["cloud_trail_event"]["eventName"] == "ConsoleLogin"
    assert result.metadata.data_hash is not None


async def test_lookup_events_empty_result(aws_credentials, invocation_id):
    mock_ct = _mock_cloudtrail_client([])

    with patch("aws.tools.cloudtrail_lookup_events.AWSClient") as mock_cls:
        mock_client = MagicMock()
        mock_client.cloudtrail_client.return_value = mock_ct
        mock_client.api_calls = 0
        mock_client._increment_calls = lambda c=1: setattr(
            mock_client, "api_calls", mock_client.api_calls + c
        )
        mock_cls.return_value = mock_client

        result = await execute(
            {"start_time": "2025-01-01T00:00:00Z", "end_time": "2025-12-31T23:59:59Z"},
            aws_credentials,
            invocation_id,
        )

    assert result.status == "success"
    assert result.data["total_count"] == 0
    assert result.data["events"] == []


async def test_lookup_events_with_event_name_filter(aws_credentials, invocation_id):
    mock_ct = _mock_cloudtrail_client([])

    with patch("aws.tools.cloudtrail_lookup_events.AWSClient") as mock_cls:
        mock_client = MagicMock()
        mock_client.cloudtrail_client.return_value = mock_ct
        mock_client.api_calls = 0
        mock_client._increment_calls = lambda c=1: setattr(
            mock_client, "api_calls", mock_client.api_calls + c
        )
        mock_cls.return_value = mock_client

        result = await execute({"event_name": "ConsoleLogin"}, aws_credentials, invocation_id)

    assert result.status == "success"
    # Verify the lookup_events call included the filter
    call_kwargs = mock_ct.lookup_events.call_args[1]
    attrs = call_kwargs["LookupAttributes"]
    assert any(a["AttributeKey"] == "EventName" for a in attrs)


async def test_lookup_events_invalid_datetime(aws_credentials, invocation_id):
    result = await execute(
        {"start_time": "not-a-date"},
        aws_credentials,
        invocation_id,
    )

    assert result.status == "error"
    assert result.error.code == "validation.invalid_parameters"


async def test_lookup_events_invalid_max_results(aws_credentials, invocation_id):
    result = await execute(
        {"max_results": 999},
        aws_credentials,
        invocation_id,
    )

    assert result.status == "error"
    assert result.error.code == "validation.invalid_parameters"
