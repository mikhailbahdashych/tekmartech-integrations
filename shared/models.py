"""Shared Pydantic models matching the mcp-tool-interface.yaml contract schemas.

These models define the data structures for credential envelopes, tool invocation
requests/responses, error objects, and per-integration credential types used by
all MCP servers in the Tekmar integration layer.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CredentialEnvelope(BaseModel):
    """Carries authentication credentials for a single MCP tool invocation.

    Structure varies by server_type. Credentials exist in memory only for the
    duration of the invocation and MUST NOT be cached, logged, or persisted.
    """

    server_type: str = Field(
        description="Identifies the credential format (aws, google_workspace, github)."
    )
    credential_mode: Literal["broker", "direct"] = Field(
        description=(
            "Whether these are short-lived temporary credentials (broker) "
            "or original credentials passed through (direct)."
        )
    )
    credential_data: dict[str, Any] = Field(
        description="The actual credential values. Structure varies by server_type."
    )


class GitHubCredentials(BaseModel):
    """GitHub-specific credential fields extracted from credential_data.

    Defined in mcp-tool-interface.yaml under credential_structures.github.
    """

    personal_access_token: str = Field(
        description="GitHub Personal Access Token with read-only permissions."
    )
    organization: str = Field(description="The GitHub organization name (login) to query against.")


class AWSCredentials(BaseModel):
    """AWS-specific credential fields extracted from credential_data.

    Defined in mcp-tool-interface.yaml under credential_structures.aws.
    In broker mode, session_token is present (temporary STS credentials).
    In direct mode, session_token is absent (long-lived access key).
    """

    access_key_id: str = Field(description="AWS access key ID.")
    secret_access_key: str = Field(description="AWS secret access key.")
    session_token: str | None = Field(
        default=None,
        description="Temporary session token from AWS STS (broker mode only).",
    )
    region: str = Field(description="AWS region to make API calls against.")


class ErrorDetail(BaseModel):
    """Additional structured error context for tool invocation errors."""

    external_status_code: int | None = Field(
        default=None,
        description="HTTP status code from the external API.",
    )
    external_error: str | None = Field(
        default=None,
        description="Sanitized error message from the external API.",
    )
    retryable: bool | None = Field(
        default=None,
        description="Whether the Execution Engine should retry this invocation.",
    )


class ToolInvocationError(BaseModel):
    """Error information in a tool invocation response.

    Present when status is 'error' or 'partial'.
    """

    code: str = Field(description="Machine-readable error code (e.g. auth.invalid_credentials).")
    message: str = Field(
        description="Human-readable error description safe to display to end users."
    )
    details: ErrorDetail | None = Field(
        default=None,
        description="Additional structured error context.",
    )


class ToolResponseMetadata(BaseModel):
    """Execution metadata captured for the transparency log."""

    started_at: str = Field(description="ISO 8601 datetime when processing began.")
    completed_at: str = Field(description="ISO 8601 datetime when processing finished.")
    duration_ms: int = Field(description="Wall-clock time in milliseconds.")
    external_api_calls: int = Field(description="Number of API calls made to the external system.")
    data_hash: str | None = Field(
        default=None,
        description="SHA-256 hash of the JSON-serialized data field.",
    )


class ToolInvocationResponse(BaseModel):
    """The payload an MCP server returns after executing a tool invocation.

    Defined in mcp-tool-interface.yaml under tool_invocation_response.
    """

    invocation_id: str = Field(description="Echoes the invocation_id from the request.")
    status: Literal["success", "error", "partial"] = Field(
        description="The outcome of the invocation."
    )
    data: dict[str, Any] | None = Field(
        default=None,
        description="The tool's output data. Present when status is success or partial.",
    )
    error: ToolInvocationError | None = Field(
        default=None,
        description="Error information. Present when status is error or partial.",
    )
    metadata: ToolResponseMetadata = Field(
        description="Execution metadata for the transparency log."
    )


class ToolInvocationRequest(BaseModel):
    """The payload the Execution Engine sends to invoke a specific tool.

    Defined in mcp-tool-interface.yaml under tool_invocation_request.
    """

    tool_name: str = Field(description="The tool to invoke.")
    parameters: dict[str, Any] = Field(
        description="Parameters conforming to the tool's input_schema."
    )
    credentials: CredentialEnvelope = Field(
        description="Credentials for authenticating with the external system."
    )
    invocation_id: str = Field(description="Unique identifier for this invocation.")
    timeout_seconds: int = Field(
        default=30,
        description="Maximum time in seconds for the invocation.",
    )
