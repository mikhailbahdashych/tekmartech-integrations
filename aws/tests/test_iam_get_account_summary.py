"""Tests for aws.tools.iam_get_account_summary."""

from moto import mock_aws

from aws.tools.iam_get_account_summary import execute


async def test_account_summary_success(aws_credentials, invocation_id):
    with mock_aws():
        # moto automatically provides a mock IAM account
        result = await execute({}, aws_credentials, invocation_id)

        assert result.status == "success"
        summary = result.data["summary_map"]
        # moto returns default summary values
        assert isinstance(summary, dict)
        assert "Users" in summary
        assert "Roles" in summary
        assert result.metadata.data_hash is not None
        assert result.metadata.external_api_calls >= 1
