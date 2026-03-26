"""Tests for aws.tools.iam_list_users."""

import boto3
from moto import mock_aws

from aws.tests.conftest import MOCK_REGION
from aws.tools.iam_list_users import execute


def _create_mock_users(iam, count=2, with_mfa=True, with_keys=True):
    """Create mock IAM users with optional MFA and access keys."""
    for i in range(count):
        username = f"user-{i}"
        iam.create_user(UserName=username)
        if with_mfa:
            iam.create_virtual_mfa_device(VirtualMFADeviceName=f"mfa-{i}")
        if with_keys:
            iam.create_access_key(UserName=username)


async def test_list_users_success(aws_credentials, invocation_id):
    with mock_aws():
        iam = boto3.client("iam", region_name=MOCK_REGION)
        _create_mock_users(iam, count=2, with_keys=True)

        result = await execute({}, aws_credentials, invocation_id)

        assert result.status == "success"
        assert result.data["total_count"] == 2
        users = result.data["users"]
        assert len(users) == 2

        user = users[0]
        assert "username" in user
        assert "user_id" in user
        assert "arn" in user
        assert "mfa_devices" in user
        assert "access_keys" in user
        assert user["access_keys"] is not None
        assert result.metadata.data_hash is not None


async def test_list_users_without_mfa(aws_credentials, invocation_id):
    with mock_aws():
        iam = boto3.client("iam", region_name=MOCK_REGION)
        iam.create_user(UserName="test-user")

        result = await execute({"include_mfa": False}, aws_credentials, invocation_id)

        assert result.status == "success"
        user = result.data["users"][0]
        assert user["mfa_devices"] is None


async def test_list_users_without_access_keys(aws_credentials, invocation_id):
    with mock_aws():
        iam = boto3.client("iam", region_name=MOCK_REGION)
        iam.create_user(UserName="test-user")

        result = await execute({"include_access_keys": False}, aws_credentials, invocation_id)

        assert result.status == "success"
        user = result.data["users"][0]
        assert user["access_keys"] is None


async def test_list_users_with_path_prefix(aws_credentials, invocation_id):
    with mock_aws():
        iam = boto3.client("iam", region_name=MOCK_REGION)
        iam.create_user(UserName="eng-user", Path="/engineering/")
        iam.create_user(UserName="ops-user", Path="/operations/")

        result = await execute(
            {"path_prefix": "/engineering/"},
            aws_credentials,
            invocation_id,
        )

        assert result.status == "success"
        assert result.data["total_count"] == 1
        assert result.data["users"][0]["username"] == "eng-user"


async def test_list_users_empty_account(aws_credentials, invocation_id):
    with mock_aws():
        result = await execute({}, aws_credentials, invocation_id)

        assert result.status == "success"
        assert result.data["total_count"] == 0
        assert result.data["users"] == []


async def test_list_users_invalid_path_prefix(aws_credentials, invocation_id):
    result = await execute({"path_prefix": "no-slash"}, aws_credentials, invocation_id)

    assert result.status == "error"
    assert result.error.code == "validation.invalid_parameters"
