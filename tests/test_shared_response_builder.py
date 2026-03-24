"""Tests for shared.response_builder."""

from datetime import UTC, datetime

from shared.models import ErrorDetail, ToolInvocationError
from shared.response_builder import (
    build_error_response,
    build_partial_response,
    build_success_response,
    compute_data_hash,
)


def test_compute_data_hash_deterministic():
    data = {"users": [{"name": "alice"}, {"name": "bob"}], "count": 2}
    hash1 = compute_data_hash(data)
    hash2 = compute_data_hash(data)
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 hex


def test_compute_data_hash_key_order_independent():
    data_a = {"b": 2, "a": 1}
    data_b = {"a": 1, "b": 2}
    assert compute_data_hash(data_a) == compute_data_hash(data_b)


def test_compute_data_hash_different_data():
    hash1 = compute_data_hash({"x": 1})
    hash2 = compute_data_hash({"x": 2})
    assert hash1 != hash2


def test_build_success_response_structure():
    started = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    data = {"repos": ["a", "b"]}
    resp = build_success_response(
        invocation_id="test-uuid",
        data=data,
        started_at=started,
        external_api_calls=3,
    )
    assert resp.invocation_id == "test-uuid"
    assert resp.status == "success"
    assert resp.data == data
    assert resp.error is None
    assert resp.metadata.external_api_calls == 3
    assert resp.metadata.data_hash is not None
    assert resp.metadata.duration_ms >= 0
    assert resp.metadata.started_at == started.isoformat()


def test_build_error_response_no_data():
    started = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    error = ToolInvocationError(
        code="auth.invalid_credentials",
        message="Bad token.",
        details=ErrorDetail(external_status_code=401, retryable=False),
    )
    resp = build_error_response(
        invocation_id="err-uuid",
        error=error,
        started_at=started,
    )
    assert resp.status == "error"
    assert resp.data is None
    assert resp.error is not None
    assert resp.error.code == "auth.invalid_credentials"
    assert resp.metadata.data_hash is None
    assert resp.metadata.external_api_calls == 0


def test_build_partial_response_has_both():
    started = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    data = {"items": [1, 2]}
    error = ToolInvocationError(
        code="rate_limit.exceeded",
        message="Rate limited mid-pagination.",
        details=ErrorDetail(retryable=True),
    )
    resp = build_partial_response(
        invocation_id="partial-uuid",
        data=data,
        error=error,
        started_at=started,
        external_api_calls=5,
    )
    assert resp.status == "partial"
    assert resp.data is not None
    assert resp.error is not None
    assert resp.metadata.data_hash is not None
    assert resp.metadata.external_api_calls == 5


def test_duration_ms_positive():
    started = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    resp = build_success_response(
        invocation_id="dur-uuid",
        data={"x": 1},
        started_at=started,
        external_api_calls=1,
    )
    assert resp.metadata.duration_ms >= 0
