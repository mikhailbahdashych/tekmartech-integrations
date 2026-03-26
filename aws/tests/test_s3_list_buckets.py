"""Tests for aws.tools.s3_list_buckets."""

import boto3
from moto import mock_aws

from aws.tests.conftest import MOCK_REGION
from aws.tools.s3_list_buckets import execute


async def test_list_buckets_success(aws_credentials, invocation_id):
    with mock_aws():
        s3 = boto3.client("s3", region_name=MOCK_REGION)
        s3.create_bucket(Bucket="test-bucket-1")
        s3.create_bucket(
            Bucket="test-bucket-eu",
            CreateBucketConfiguration={"LocationConstraint": "eu-west-1"},
        )

        result = await execute({}, aws_credentials, invocation_id)

        assert result.status == "success"
        assert result.data["total_count"] == 2

        buckets = result.data["buckets"]
        names = {b["name"] for b in buckets}
        assert "test-bucket-1" in names
        assert "test-bucket-eu" in names

        # Verify region lookup
        eu_bucket = next(b for b in buckets if b["name"] == "test-bucket-eu")
        assert eu_bucket["region"] == "eu-west-1"

        # us-east-1 bucket: LocationConstraint is None which maps to us-east-1
        us_bucket = next(b for b in buckets if b["name"] == "test-bucket-1")
        assert us_bucket["region"] == "us-east-1"

        assert result.metadata.data_hash is not None


async def test_list_buckets_empty(aws_credentials, invocation_id):
    with mock_aws():
        result = await execute({}, aws_credentials, invocation_id)

        assert result.status == "success"
        assert result.data["total_count"] == 0
        assert result.data["buckets"] == []
