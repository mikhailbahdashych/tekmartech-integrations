"""Build standardized error responses per the mcp-tool-interface.yaml contract.

Provides error code mapping from HTTP status codes to contract error codes,
error message sanitization to strip credential values, and convenience
constructors for common error types.
"""

from __future__ import annotations

import re

from shared.models import ErrorDetail, ToolInvocationError

# Patterns that may contain credential fragments in error messages.
_SENSITIVE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ghp_[A-Za-z0-9]{36,}"),  # Classic GitHub PAT
    re.compile(r"github_pat_[A-Za-z0-9_]{22,}"),  # Fine-grained GitHub PAT
    re.compile(r"gho_[A-Za-z0-9]{36,}"),  # GitHub OAuth token
    re.compile(r"ghu_[A-Za-z0-9]{36,}"),  # GitHub user-to-server token
    re.compile(r"ghs_[A-Za-z0-9]{36,}"),  # GitHub server-to-server token
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+"),  # Authorization header value
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key ID
    re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9/+]{40,}(?![A-Za-z0-9])"),  # Long base64 secrets
]


def sanitize_error_message(message: str) -> str:
    """Strip token-like or key-like strings from an error message.

    Args:
        message: The raw error message that may contain credential fragments.

    Returns:
        The message with sensitive strings replaced by [REDACTED].
    """
    sanitized = message
    for pattern in _SENSITIVE_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized


def map_http_error(status_code: int, message: str = "") -> ToolInvocationError:
    """Map an HTTP status code to a contract-defined error code.

    Args:
        status_code: The HTTP status code from the external API.
        message: Optional error message (will be sanitized).

    Returns:
        A ToolInvocationError with the appropriate code and retryable flag.
    """
    sanitized = sanitize_error_message(message) if message else ""

    if status_code == 401:
        return ToolInvocationError(
            code="auth.invalid_credentials",
            message=sanitized or "Authentication failed: invalid credentials.",
            details=ErrorDetail(
                external_status_code=status_code,
                retryable=False,
            ),
        )

    if status_code == 403:
        return ToolInvocationError(
            code="auth.insufficient_permissions",
            message=sanitized or "Insufficient permissions for the requested operation.",
            details=ErrorDetail(
                external_status_code=status_code,
                retryable=False,
            ),
        )

    if status_code == 429:
        return ToolInvocationError(
            code="rate_limit.exceeded",
            message=sanitized or "Rate limit exceeded on external API.",
            details=ErrorDetail(
                external_status_code=status_code,
                retryable=True,
            ),
        )

    if status_code == 503:
        return ToolInvocationError(
            code="external.service_unavailable",
            message=sanitized or "External service is temporarily unavailable.",
            details=ErrorDetail(
                external_status_code=status_code,
                retryable=True,
            ),
        )

    if 500 <= status_code < 600:
        return ToolInvocationError(
            code="external.api_error",
            message=sanitized or f"External API error (HTTP {status_code}).",
            details=ErrorDetail(
                external_status_code=status_code,
                retryable=True,
            ),
        )

    # Fallback for unexpected status codes
    return ToolInvocationError(
        code="external.api_error",
        message=sanitized or f"Unexpected HTTP status code: {status_code}.",
        details=ErrorDetail(
            external_status_code=status_code,
            retryable=False,
        ),
    )


def map_boto3_error(error_code: str, message: str = "") -> ToolInvocationError:
    """Map a boto3 ClientError code to a contract-defined error.

    Args:
        error_code: The boto3 error code (e.g. 'InvalidClientTokenId').
        message: Optional error message (will be sanitized).

    Returns:
        A ToolInvocationError with the appropriate code and retryable flag.
    """
    sanitized = sanitize_error_message(message) if message else ""

    auth_invalid = {
        "InvalidClientTokenId",
        "SignatureDoesNotMatch",
        "AuthFailure",
        "UnrecognizedClientException",
    }
    auth_expired = {"ExpiredToken", "ExpiredTokenException", "RequestExpired"}
    auth_permission = {
        "AccessDenied",
        "AccessDeniedException",
        "UnauthorizedAccess",
        "ClientError.403",
    }
    throttle = {
        "Throttling",
        "ThrottlingException",
        "RequestLimitExceeded",
        "TooManyRequestsException",
    }

    if error_code in auth_invalid:
        return ToolInvocationError(
            code="auth.invalid_credentials",
            message=sanitized or "Authentication failed: invalid AWS credentials.",
            details=ErrorDetail(retryable=False),
        )
    if error_code in auth_expired:
        return ToolInvocationError(
            code="auth.expired_credentials",
            message=sanitized or "AWS credentials have expired.",
            details=ErrorDetail(retryable=False),
        )
    if error_code in auth_permission:
        return ToolInvocationError(
            code="auth.insufficient_permissions",
            message=sanitized or "Insufficient AWS IAM permissions.",
            details=ErrorDetail(retryable=False),
        )
    if error_code in throttle:
        return ToolInvocationError(
            code="rate_limit.exceeded",
            message=sanitized or "AWS API rate limit exceeded.",
            details=ErrorDetail(retryable=True),
        )

    # Default: treat as external API error
    return ToolInvocationError(
        code="external.api_error",
        message=sanitized or f"AWS API error: {error_code}.",
        details=ErrorDetail(retryable=True),
    )


def map_google_api_error(status_code: int, message: str = "") -> ToolInvocationError:
    """Map a Google API HTTP error to a contract-defined error.

    The google-api-python-client raises HttpError with an HTTP status code.
    This maps those to the contract error codes.

    Args:
        status_code: The HTTP status code from the Google API.
        message: Optional error message (will be sanitized).

    Returns:
        A ToolInvocationError with the appropriate code and retryable flag.
    """
    sanitized = sanitize_error_message(message) if message else ""

    if status_code == 401:
        return ToolInvocationError(
            code="auth.invalid_credentials",
            message=sanitized or "Google API authentication failed.",
            details=ErrorDetail(external_status_code=status_code, retryable=False),
        )
    if status_code == 403:
        return ToolInvocationError(
            code="auth.insufficient_permissions",
            message=sanitized or "Insufficient Google API permissions.",
            details=ErrorDetail(external_status_code=status_code, retryable=False),
        )
    if status_code == 429:
        return ToolInvocationError(
            code="rate_limit.exceeded",
            message=sanitized or "Google API rate limit exceeded.",
            details=ErrorDetail(external_status_code=status_code, retryable=True),
        )
    if status_code == 503:
        return ToolInvocationError(
            code="external.service_unavailable",
            message=sanitized or "Google API service unavailable.",
            details=ErrorDetail(external_status_code=status_code, retryable=True),
        )
    if 500 <= status_code < 600:
        return ToolInvocationError(
            code="external.api_error",
            message=sanitized or f"Google API error (HTTP {status_code}).",
            details=ErrorDetail(external_status_code=status_code, retryable=True),
        )
    return ToolInvocationError(
        code="external.api_error",
        message=sanitized or f"Unexpected Google API status: {status_code}.",
        details=ErrorDetail(external_status_code=status_code, retryable=False),
    )


def format_validation_error(message: str) -> ToolInvocationError:
    """Create a validation.invalid_parameters error.

    Args:
        message: Human-readable description of the validation failure.

    Returns:
        A ToolInvocationError with code validation.invalid_parameters.
    """
    return ToolInvocationError(
        code="validation.invalid_parameters",
        message=sanitize_error_message(message),
        details=ErrorDetail(retryable=False),
    )


def format_internal_error(message: str) -> ToolInvocationError:
    """Create an internal.server_error error.

    Args:
        message: Human-readable description of the internal error.

    Returns:
        A ToolInvocationError with code internal.server_error.
    """
    return ToolInvocationError(
        code="internal.server_error",
        message=sanitize_error_message(message),
        details=ErrorDetail(retryable=False),
    )


def format_timeout_error() -> ToolInvocationError:
    """Create a timeout.invocation_timeout error.

    Returns:
        A ToolInvocationError with code timeout.invocation_timeout.
    """
    return ToolInvocationError(
        code="timeout.invocation_timeout",
        message="Tool invocation timed out.",
        details=ErrorDetail(retryable=True),
    )
