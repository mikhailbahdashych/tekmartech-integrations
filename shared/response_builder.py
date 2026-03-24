"""Build tool_invocation_response objects with metadata per the contract.

Provides builders for success, error, and partial responses that compute
timing metadata and data hashes for the transparency log.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from shared.models import (
    ToolInvocationError,
    ToolInvocationResponse,
    ToolResponseMetadata,
)


def compute_data_hash(data: dict[str, Any]) -> str:
    """Compute SHA-256 hash of JSON-serialized data for the transparency log.

    Uses deterministic serialization (sorted keys, compact separators) so the
    same data always produces the same hash regardless of key insertion order.

    Args:
        data: The response data dict to hash.

    Returns:
        Hex-encoded SHA-256 hash string.
    """
    serialized = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _build_metadata(
    started_at: datetime,
    external_api_calls: int,
    data: dict[str, Any] | None,
) -> ToolResponseMetadata:
    """Build the metadata object with timing and hash.

    Args:
        started_at: When processing began (UTC).
        external_api_calls: Number of external API calls made.
        data: Response data (used to compute data_hash), or None.

    Returns:
        A populated ToolResponseMetadata instance.
    """
    completed_at = datetime.now(UTC)
    duration_ms = int((completed_at - started_at).total_seconds() * 1000)
    data_hash = compute_data_hash(data) if data is not None else None

    return ToolResponseMetadata(
        started_at=started_at.isoformat(),
        completed_at=completed_at.isoformat(),
        duration_ms=duration_ms,
        external_api_calls=external_api_calls,
        data_hash=data_hash,
    )


def build_success_response(
    invocation_id: str,
    data: dict[str, Any],
    started_at: datetime,
    external_api_calls: int,
) -> ToolInvocationResponse:
    """Build a success response with computed metadata.

    Args:
        invocation_id: UUID echoed from the request.
        data: The tool's output data conforming to its output_schema.
        started_at: UTC datetime when processing began.
        external_api_calls: Total external API calls made.

    Returns:
        A ToolInvocationResponse with status "success".
    """
    return ToolInvocationResponse(
        invocation_id=invocation_id,
        status="success",
        data=data,
        metadata=_build_metadata(started_at, external_api_calls, data),
    )


def build_error_response(
    invocation_id: str,
    error: ToolInvocationError,
    started_at: datetime,
    external_api_calls: int = 0,
) -> ToolInvocationResponse:
    """Build an error response with metadata.

    Args:
        invocation_id: UUID echoed from the request.
        error: The structured error information.
        started_at: UTC datetime when processing began.
        external_api_calls: Total external API calls made before the error.

    Returns:
        A ToolInvocationResponse with status "error".
    """
    return ToolInvocationResponse(
        invocation_id=invocation_id,
        status="error",
        error=error,
        metadata=_build_metadata(started_at, external_api_calls, None),
    )


def build_partial_response(
    invocation_id: str,
    data: dict[str, Any],
    error: ToolInvocationError,
    started_at: datetime,
    external_api_calls: int,
) -> ToolInvocationResponse:
    """Build a partial response (some data collected, but an error occurred).

    Args:
        invocation_id: UUID echoed from the request.
        data: Whatever data was collected before the error.
        error: The structured error information.
        started_at: UTC datetime when processing began.
        external_api_calls: Total external API calls made.

    Returns:
        A ToolInvocationResponse with status "partial".
    """
    return ToolInvocationResponse(
        invocation_id=invocation_id,
        status="partial",
        data=data,
        error=error,
        metadata=_build_metadata(started_at, external_api_calls, data),
    )
