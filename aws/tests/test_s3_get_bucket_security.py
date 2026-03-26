"""Tests for aws.tools.s3_get_bucket_security."""

import json

import boto3
from moto import mock_aws

from aws.tests.conftest import MOCK_REGION
from aws.tools.s3_get_bucket_security import execute


async def test_bucket_security_full_config(aws_credentials, invocation_id):
    with mock_aws():
        s3 = boto3.client("s3", region_name=MOCK_REGION)
        s3.create_bucket(Bucket="secure-bucket")

        # Set public access block
        s3.put_public_access_block(
            Bucket="secure-bucket",
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            },
        )

        # Set bucket policy
        policy = json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Deny",
                        "Principal": "*",
                        "Action": "s3:*",
                        "Resource": "arn:aws:s3:::secure-bucket/*",
                        "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                    }
                ],
            }
        )
        s3.put_bucket_policy(Bucket="secure-bucket", Policy=policy)

        # Set encryption
        s3.put_bucket_encryption(
            Bucket="secure-bucket",
            ServerSideEncryptionConfiguration={
                "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
            },
        )

        # Set versioning
        s3.put_bucket_versioning(
            Bucket="secure-bucket",
            VersioningConfiguration={"Status": "Enabled"},
        )

        result = await execute({"bucket_name": "secure-bucket"}, aws_credentials, invocation_id)

        assert result.status == "success"
        data = result.data
        assert data["bucket_name"] == "secure-bucket"
        assert data["public_access_block"] is not None
        assert data["public_access_block"]["BlockPublicAcls"] is True
        assert data["bucket_policy"] is not None
        assert data["encryption"] is not None
        assert data["versioning"]["status"] == "Enabled"
        assert result.metadata.data_hash is not None


async def test_bucket_security_minimal_config(aws_credentials, invocation_id):
    """A bucket with no special configs — should return nulls gracefully."""
    with mock_aws():
        s3 = boto3.client("s3", region_name=MOCK_REGION)
        s3.create_bucket(Bucket="bare-bucket")

        result = await execute({"bucket_name": "bare-bucket"}, aws_credentials, invocation_id)

        assert result.status == "success"
        data = result.data
        assert data["bucket_name"] == "bare-bucket"
        # No policy or encryption set — should be None
        assert data["bucket_policy"] is None
        assert data["encryption"] is None
        assert data["versioning"]["status"] == "Disabled"


async def test_bucket_security_missing_name(aws_credentials, invocation_id):
    result = await execute({}, aws_credentials, invocation_id)

    assert result.status == "error"
    assert result.error.code == "validation.invalid_parameters"
