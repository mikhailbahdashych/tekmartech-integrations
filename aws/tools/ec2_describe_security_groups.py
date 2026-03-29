"""Implements aws.ec2_describe_security_groups from mcp-tool-interface.yaml.

Lists security groups with their inbound and outbound rules. Flattens
IpPermissions into a human-readable format with protocol, port range,
and source/destination information. Uses paginator for complete listing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from botocore.exceptions import ClientError

from aws.client import AWSClient, handle_client_error, run_boto3
from shared.credential_handler import extract_aws_credentials
from shared.models import CredentialEnvelope, ToolInvocationResponse
from shared.response_builder import build_error_response, build_success_response

logger = structlog.get_logger()

definition: dict[str, Any] = {
    "tool_name": "aws.ec2_describe_security_groups",
    "display_name": "Describe Security Groups",
    "description": (
        "List security groups with their inbound and outbound rules. "
        "Used for network access review."
    ),
    "category": "network",
    "input_schema": {
        "type": "object",
        "properties": {
            "vpc_id": {
                "type": "string",
                "description": "Filter by VPC ID.",
            },
            "group_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filter by specific security group IDs.",
            },
        },
        "required": [],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "security_groups": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "group_id": {"type": "string"},
                        "group_name": {"type": "string"},
                        "description": {"type": "string"},
                        "vpc_id": {"type": "string"},
                        "inbound_rules": {"type": "array", "items": {"type": "object"}},
                        "outbound_rules": {"type": "array", "items": {"type": "object"}},
                    },
                },
            },
            "total_count": {"type": "integer"},
        },
    },
}


def _format_port_range(perm: dict[str, Any]) -> str:
    """Format a port range from an IpPermission entry.

    Args:
        perm: An IpPermission dict with FromPort/ToPort.

    Returns:
        A human-readable port range string.
    """
    protocol = perm.get("IpProtocol", "-1")
    if protocol == "-1":
        return "All traffic"

    from_port = perm.get("FromPort", 0)
    to_port = perm.get("ToPort", 0)

    if from_port == to_port:
        return str(from_port)
    return f"{from_port}-{to_port}"


def _flatten_rules(permissions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten IpPermissions into human-readable rule dicts.

    Each IpPermission can have multiple source ranges (IPv4, IPv6, security
    group refs, prefix lists). We expand each into a separate rule entry.

    Args:
        permissions: List of IpPermission dicts from EC2 API.

    Returns:
        List of flattened rule dicts.
    """
    rules: list[dict[str, Any]] = []
    for perm in permissions:
        protocol = perm.get("IpProtocol", "-1")
        if protocol == "-1":
            protocol = "all"
        port_range = _format_port_range(perm)

        # IPv4 CIDR ranges
        for ip_range in perm.get("IpRanges", []):
            rules.append(
                {
                    "protocol": protocol,
                    "port_range": port_range,
                    "source": ip_range.get("CidrIp", ""),
                    "description": ip_range.get("Description", ""),
                }
            )

        # IPv6 CIDR ranges
        for ip_range in perm.get("Ipv6Ranges", []):
            rules.append(
                {
                    "protocol": protocol,
                    "port_range": port_range,
                    "source": ip_range.get("CidrIpv6", ""),
                    "description": ip_range.get("Description", ""),
                }
            )

        # Security group references
        for sg_ref in perm.get("UserIdGroupPairs", []):
            source_id = sg_ref.get("GroupId", "")
            rules.append(
                {
                    "protocol": protocol,
                    "port_range": port_range,
                    "source": source_id,
                    "description": sg_ref.get("Description", ""),
                }
            )

        # Prefix lists
        for prefix in perm.get("PrefixListIds", []):
            rules.append(
                {
                    "protocol": protocol,
                    "port_range": port_range,
                    "source": prefix.get("PrefixListId", ""),
                    "description": prefix.get("Description", ""),
                }
            )

    return rules


async def execute(
    parameters: dict[str, Any],
    credentials: CredentialEnvelope,
    invocation_id: str,
    timeout_seconds: int = 30,
) -> ToolInvocationResponse:
    """Execute the aws.ec2_describe_security_groups tool.

    Args:
        parameters: Tool input (vpc_id, group_ids).
        credentials: Credential envelope with AWS credentials.
        invocation_id: Unique identifier for this invocation.
        timeout_seconds: Maximum execution time.

    Returns:
        A ToolInvocationResponse with security group data or error.
    """
    started_at = datetime.now(UTC)

    logger.debug(
        "tool_invocation_start",
        module="aws",
        action="ec2_describe_security_groups",
        tool_name="aws.ec2_describe_security_groups",
    )

    aws_creds = extract_aws_credentials(credentials)
    client = AWSClient(aws_creds)
    ec2 = client.ec2_client()

    # Build filters
    filters: list[dict[str, Any]] = []
    if "vpc_id" in parameters:
        filters.append({"Name": "vpc-id", "Values": [parameters["vpc_id"]]})

    paginator_kwargs: dict[str, Any] = {}
    if filters:
        paginator_kwargs["Filters"] = filters
    if "group_ids" in parameters:
        paginator_kwargs["GroupIds"] = parameters["group_ids"]

    try:
        paginator = ec2.get_paginator("describe_security_groups")

        def _paginate() -> list[dict[str, Any]]:
            groups: list[dict[str, Any]] = []
            for page in paginator.paginate(**paginator_kwargs):
                client._increment_calls()
                groups.extend(page.get("SecurityGroups", []))
            return groups

        raw_groups = await run_boto3(client, lambda: _paginate())
    except ClientError as exc:
        return build_error_response(
            invocation_id=invocation_id,
            error=handle_client_error(exc),
            started_at=started_at,
            external_api_calls=client.api_calls,
        )

    security_groups = [
        {
            "group_id": sg.get("GroupId"),
            "group_name": sg.get("GroupName"),
            "description": sg.get("Description"),
            "vpc_id": sg.get("VpcId"),
            "inbound_rules": _flatten_rules(sg.get("IpPermissions", [])),
            "outbound_rules": _flatten_rules(sg.get("IpPermissionsEgress", [])),
        }
        for sg in raw_groups
    ]

    data = {"security_groups": security_groups, "total_count": len(security_groups)}

    logger.info(
        "tool_invocation_success",
        module="aws",
        action="ec2_describe_security_groups",
        tool_name="aws.ec2_describe_security_groups",
        total_count=len(security_groups),
        api_calls=client.api_calls,
    )

    return build_success_response(
        invocation_id=invocation_id,
        data=data,
        started_at=started_at,
        external_api_calls=client.api_calls,
    )
