"""Tests for aws.tools.iam_list_roles."""

import json

import boto3
from moto import mock_aws

from aws.tests.conftest import MOCK_REGION
from aws.tools.iam_list_roles import execute

TRUST_POLICY = json.dumps(
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "ec2.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }
)

IAM_POLICY = json.dumps(
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["s3:GetObject", "s3:ListBucket"],
                "Resource": "*",
            }
        ],
    }
)


async def test_list_roles_success(aws_credentials, invocation_id):
    with mock_aws():
        iam = boto3.client("iam", region_name=MOCK_REGION)
        iam.create_role(
            RoleName="test-role",
            AssumeRolePolicyDocument=TRUST_POLICY,
        )
        # Create and attach a custom policy (moto doesn't have AWS managed policies)
        policy_resp = iam.create_policy(
            PolicyName="TestReadOnly",
            PolicyDocument=IAM_POLICY,
        )
        iam.attach_role_policy(
            RoleName="test-role",
            PolicyArn=policy_resp["Policy"]["Arn"],
        )

        result = await execute({}, aws_credentials, invocation_id)

        assert result.status == "success"
        # moto may include default roles; find ours
        roles = result.data["roles"]
        test_role = next((r for r in roles if r["role_name"] == "test-role"), None)
        assert test_role is not None
        assert test_role["arn"] is not None
        assert test_role["assume_role_policy_document"] is not None
        assert len(test_role["attached_policies"]) >= 1
        assert result.metadata.data_hash is not None


async def test_list_roles_with_path_prefix(aws_credentials, invocation_id):
    with mock_aws():
        iam = boto3.client("iam", region_name=MOCK_REGION)
        iam.create_role(
            RoleName="service-role",
            AssumeRolePolicyDocument=TRUST_POLICY,
            Path="/service-roles/",
        )
        iam.create_role(
            RoleName="admin-role",
            AssumeRolePolicyDocument=TRUST_POLICY,
            Path="/admin/",
        )

        result = await execute({"path_prefix": "/service-roles/"}, aws_credentials, invocation_id)

        assert result.status == "success"
        names = [r["role_name"] for r in result.data["roles"]]
        assert "service-role" in names
        assert "admin-role" not in names
