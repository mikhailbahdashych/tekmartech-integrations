"""Tests for aws.tools.ec2_describe_security_groups."""

import boto3
from moto import mock_aws

from aws.tests.conftest import MOCK_REGION
from aws.tools.ec2_describe_security_groups import execute


async def test_describe_security_groups_success(aws_credentials, invocation_id):
    with mock_aws():
        ec2 = boto3.client("ec2", region_name=MOCK_REGION)

        # Create a VPC and security group
        vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
        vpc_id = vpc["Vpc"]["VpcId"]

        sg = ec2.create_security_group(
            GroupName="test-sg",
            Description="Test security group",
            VpcId=vpc_id,
        )
        sg_id = sg["GroupId"]

        # Add inbound rule
        ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 443,
                    "ToPort": 443,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "HTTPS"}],
                },
            ],
        )

        result = await execute({}, aws_credentials, invocation_id)

        assert result.status == "success"
        groups = result.data["security_groups"]
        assert len(groups) >= 1

        # Find our group
        test_sg = next((g for g in groups if g["group_id"] == sg_id), None)
        assert test_sg is not None
        assert test_sg["group_name"] == "test-sg"
        assert test_sg["vpc_id"] == vpc_id

        # Check inbound rules
        inbound = test_sg["inbound_rules"]
        https_rule = next((r for r in inbound if r["port_range"] == "443"), None)
        assert https_rule is not None
        assert https_rule["protocol"] == "tcp"
        assert https_rule["source"] == "0.0.0.0/0"

        assert result.metadata.data_hash is not None


async def test_describe_security_groups_vpc_filter(aws_credentials, invocation_id):
    with mock_aws():
        ec2 = boto3.client("ec2", region_name=MOCK_REGION)

        vpc1 = ec2.create_vpc(CidrBlock="10.0.0.0/16")
        vpc1_id = vpc1["Vpc"]["VpcId"]
        vpc2 = ec2.create_vpc(CidrBlock="10.1.0.0/16")
        vpc2_id = vpc2["Vpc"]["VpcId"]

        ec2.create_security_group(GroupName="sg-vpc1", Description="VPC1 SG", VpcId=vpc1_id)
        ec2.create_security_group(GroupName="sg-vpc2", Description="VPC2 SG", VpcId=vpc2_id)

        result = await execute({"vpc_id": vpc1_id}, aws_credentials, invocation_id)

        assert result.status == "success"
        group_vpcs = {g["vpc_id"] for g in result.data["security_groups"]}
        assert vpc2_id not in group_vpcs


async def test_describe_security_groups_rule_flattening(aws_credentials, invocation_id):
    """Test that rules with multiple sources are flattened into separate entries."""
    with mock_aws():
        ec2 = boto3.client("ec2", region_name=MOCK_REGION)

        vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
        vpc_id = vpc["Vpc"]["VpcId"]

        sg = ec2.create_security_group(
            GroupName="multi-source-sg", Description="Test", VpcId=vpc_id
        )
        sg_id = sg["GroupId"]

        # Rule with two CIDR ranges
        ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 80,
                    "ToPort": 80,
                    "IpRanges": [
                        {"CidrIp": "10.0.0.0/8"},
                        {"CidrIp": "172.16.0.0/12"},
                    ],
                },
            ],
        )

        result = await execute({"group_ids": [sg_id]}, aws_credentials, invocation_id)

        assert result.status == "success"
        test_sg = next((g for g in result.data["security_groups"] if g["group_id"] == sg_id), None)
        assert test_sg is not None

        # Should have 2 flattened inbound rules (one per CIDR)
        port_80_rules = [r for r in test_sg["inbound_rules"] if r["port_range"] == "80"]
        assert len(port_80_rules) == 2
        sources = {r["source"] for r in port_80_rules}
        assert "10.0.0.0/8" in sources
        assert "172.16.0.0/12" in sources
