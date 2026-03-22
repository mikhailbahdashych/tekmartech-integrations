# CLAUDE.md — tekmar-integrations

## Identity

You are building the **Integration Layer** for Tekmar, an AI-powered
infrastructure query and analysis engine for security and compliance teams.
This repository contains MCP (Model Context Protocol) servers — one per
external system — that expose read-only query tools the Pipeline Service
uses to retrieve data from customers' infrastructure.

Each MCP server is a small, self-contained Python program that:
1. Declares the tools it offers (tool name, description, input/output schemas).
2. Receives tool invocation requests from the Pipeline Service.
3. Authenticates with the external system using provided credentials.
4. Executes the read-only API call.
5. Returns structured results.

This repository is the only component that makes direct API calls to
external systems (AWS, Google Workspace, GitHub). No other Tekmar
component communicates with customer infrastructure.

**Two invariants are absolute:**
- **Read-only access** (Architectural Invariant #2). Every tool performs
  read operations only. No tool may create, modify, or delete anything
  in a customer's external infrastructure. This is non-negotiable.
- **No credential persistence** (Architectural Invariant #3). Credentials
  arrive with each tool invocation and are used for that single call only.
  MCP servers never cache, store, log, or persist credentials in any form.

---

## Contract References

| Contract | Path | Role in this project |
|----------|------|----------------------|
| Architecture Contract | `../tekmar-infrastructure/contracts/architecture.md` | Integration Layer description (section 4.4), credential handling (section 6.3), and invariants #2 and #3. |
| MCP Tool Interface | `../tekmar-infrastructure/contracts/mcp-tool-interface.yaml` | **Primary contract.** Defines everything this repository implements: MCP server registration (section 1), tool_definition schema, tool_invocation_request and tool_invocation_response schemas (section 3), credential_envelope and per-type credential_structures, error codes, rate limit advisory format, pagination declaration, and the MVP tool inventory listing every tool to implement. |

This repository does NOT reference `public-api.yaml`, `internal-api.yaml`,
or `data-model.yaml`. MCP servers have no knowledge of the public API,
the internal API protocol, or the database.

---

## Technology Stack

| Concern | Choice |
|---------|--------|
| Language | Python 3.11+ |
| MCP SDK | mcp Python SDK (official) |
| Transport | stdio (MVP: servers run as child processes of the Pipeline Service) |
| AWS SDK | boto3 |
| Google SDK | google-api-python-client + google-auth |
| GitHub SDK | httpx (direct GitHub REST API calls, no wrapper library needed) |
| Validation | Pydantic v2 models |
| Testing | pytest + moto (AWS mocking) + responses/respx (HTTP mocking) |

---

## Repository Structure

```
tekmar-integrations/
├── CLAUDE.md
├── shared/                              ← Common code used by all MCP servers
│   ├── credential_handler.py            ← Parse credential_envelope, extract per-type fields
│   ├── error_formatting.py              ← Build standardized error responses per contract
│   ├── rate_limiter.py                  ← Token bucket rate limiter for external API calls
│   ├── response_builder.py              ← Build tool_invocation_response with metadata
│   ├── pagination.py                    ← Common pagination helpers
│   └── models.py                        ← Shared Pydantic models (credential_envelope, response)
│
├── aws/                                 ← AWS MCP server
│   ├── server.py                        ← MCP server entry point, tool registration
│   ├── client.py                        ← boto3 client creation from credentials
│   ├── tools/
│   │   ├── iam_list_users.py            ← aws.iam_list_users
│   │   ├── iam_list_roles.py            ← aws.iam_list_roles
│   │   ├── iam_get_account_summary.py   ← aws.iam_get_account_summary
│   │   ├── cloudtrail_lookup_events.py  ← aws.cloudtrail_lookup_events
│   │   ├── s3_list_buckets.py           ← aws.s3_list_buckets
│   │   ├── s3_get_bucket_security.py    ← aws.s3_get_bucket_security
│   │   └── ec2_describe_security_groups.py ← aws.ec2_describe_security_groups
│   └── tests/
│       └── ...
│
├── google_workspace/                    ← Google Workspace MCP server
│   ├── server.py
│   ├── client.py                        ← Google API client creation from service account
│   ├── tools/
│   │   ├── list_users.py                ← google_workspace.list_users
│   │   ├── get_user_mfa_status.py       ← google_workspace.get_user_mfa_status
│   │   ├── list_user_tokens.py          ← google_workspace.list_user_tokens
│   │   └── list_login_events.py         ← google_workspace.list_login_events
│   └── tests/
│       └── ...
│
├── github/                              ← GitHub MCP server
│   ├── server.py
│   ├── client.py                        ← httpx client with PAT authentication
│   ├── tools/
│   │   ├── list_organization_members.py ← github.list_organization_members
│   │   ├── list_repositories.py         ← github.list_repositories
│   │   ├── get_branch_protection.py     ← github.get_branch_protection
│   │   ├── list_pull_requests.py        ← github.list_pull_requests
│   │   └── list_repository_collaborators.py ← github.list_repository_collaborators
│   └── tests/
│       └── ...
│
├── pyproject.toml
├── requirements.txt
└── Dockerfile
```

---

## Tool Implementation Pattern

Every tool follows the same pattern. This consistency is critical because
the Execution Engine treats all tools identically regardless of which
external system they query.

**1. Tool declaration.** Each tool declares its metadata conforming to the
tool_definition schema in `mcp-tool-interface.yaml`: tool_name (prefixed
with server_type, e.g., `aws.iam_list_users`), display_name, description,
category, input_schema (JSON Schema for parameters), output_schema
(JSON Schema for returned data), and optionally rate_limit and pagination
information.

**2. Input validation.** Before making any external API call, validate the
incoming parameters against the tool's input_schema. Reject invalid
parameters with error code `validation.invalid_parameters`.

**3. Credential extraction.** Read the credential_envelope from the
invocation request. Use `shared/credential_handler.py` to extract the
type-specific credential fields. Create an authenticated API client
(boto3 session, Google API client, or httpx client with auth header).

**4. API call execution.** Make the read-only API call to the external
system. Handle pagination if the tool declares pagination support and
the invocation request does not explicitly disable it.

**5. Response construction.** Build a `tool_invocation_response` using
`shared/response_builder.py`:
- On success: set status `"success"`, include the data conforming to the
  tool's output_schema, and populate metadata (started_at, completed_at,
  duration_ms, external_api_calls, data_hash).
- On error: set status `"error"`, include the error object with
  appropriate code, message, and details (external_status_code, retryable
  flag). Sanitize any credential values from external error messages.
- On partial success (e.g., pagination interrupted by rate limit): set
  status `"partial"`, include whatever data was collected, and include
  the error object.

**6. Cleanup.** Drop all references to credentials. The authenticated
client is garbage-collected after the response is returned.

---

## MCP Server Registration

Each server's `server.py` registers the server with the MCP SDK,
declaring its server_type, server_name, server_version, description,
and all tools. Example structure:

```python
# aws/server.py
from mcp import Server
from .tools import (
    iam_list_users, iam_list_roles, iam_get_account_summary,
    cloudtrail_lookup_events, s3_list_buckets, s3_get_bucket_security,
    ec2_describe_security_groups,
)

server = Server(name="tekmar-aws-mcp")

# Register each tool with its handler
@server.tool("aws.iam_list_users")
async def handle_iam_list_users(params, credentials):
    return await iam_list_users.execute(params, credentials)

# ... register all tools
```

The server_type must exactly match the integration type values in the
data model (`aws`, `google_workspace`, `github`). The Pipeline Service
uses this to route tool invocations to the correct MCP server.

---

## Credential Handling Per Server Type

Each server type receives credentials in a specific structure defined
in `mcp-tool-interface.yaml` under `credential_structures`:

**AWS credentials:**
- `access_key_id` (string, required)
- `secret_access_key` (string, required)
- `session_token` (string, optional — present in broker mode)
- `region` (string, required)

Create a boto3 session with these credentials. If session_token is
present, include it (temporary credentials from STS). The region
determines which AWS regional endpoint to call.

**Google Workspace credentials:**
- `service_account_json` (string, required — full service account key JSON)
- `delegated_email` (string, optional — for domain-wide delegation)

Parse the service_account_json, create a Google credentials object,
and if delegated_email is provided, use domain-wide delegation to
impersonate that user.

**GitHub credentials:**
- `personal_access_token` (string, required)
- `organization` (string, required)

Create an httpx client with the PAT in the Authorization header
(`Bearer <token>`). All GitHub API calls are scoped to the specified
organization.

---

## Error Code Mapping

When external API calls fail, map the failure to the standardized error
codes defined in `mcp-tool-interface.yaml` under
`tool_invocation_response.error`:

| External failure | Error code | Retryable |
|------------------|------------|-----------|
| Invalid credentials (401/403) | auth.invalid_credentials | No |
| Insufficient permissions (403) | auth.insufficient_permissions | No |
| Expired temporary credentials | auth.expired_credentials | No |
| Rate limit exceeded (429) | rate_limit.exceeded | Yes |
| Invocation exceeded timeout | timeout.invocation_timeout | Yes |
| External API error (5xx) | external.api_error | Yes |
| External service down | external.service_unavailable | Yes |
| Invalid parameters passed | validation.invalid_parameters | No |
| Unexpected internal error | internal.server_error | No |

The `retryable` flag tells the Execution Engine whether to retry the
invocation. Retries are the Execution Engine's responsibility, not the
MCP server's. The MCP server reports the error; the engine decides
whether to retry.

**Error message sanitization:** External API error messages may contain
credential fragments, request IDs, or internal details. Before including
an external error message in the response, strip any string that looks
like a token, key, or secret. When in doubt, replace the external
message with a generic description.

---

## Testing Strategy

Each tool should have unit tests that verify:
- Correct API calls are made with expected parameters (using moto for
  AWS, responses/respx for HTTP-based services).
- Response data is correctly structured according to the output_schema.
- Pagination is handled correctly (multi-page responses assembled).
- Error cases produce correctly formatted error responses.
- Credentials are never present in any logged output or error message.

Integration tests (against real APIs with test accounts) are valuable
but not required for the MVP. The unit tests with mocked external APIs
provide sufficient coverage for development.

---

## Environment Variables

MCP servers do not have their own environment variables for credentials
(credentials arrive per-invocation). Server-level configuration:

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Logging level | INFO |
| `AWS_MAX_RETRIES` | boto3 retry limit for transient failures | 3 |
| `GITHUB_API_BASE_URL` | GitHub API base URL | https://api.github.com |
| `GOOGLE_API_TIMEOUT` | Timeout for Google API calls in seconds | 30 |

---

## Coding Conventions

**One tool, one file.** Each tool implementation lives in its own file
within the server's `tools/` directory. The file exports an `execute`
function and a `definition` object (the tool_definition metadata).

**Shared code in shared/.** Cross-cutting concerns (credential parsing,
error formatting, rate limiting, response building) live in the shared
directory. MCP servers import from shared, never from each other.

**No cross-server imports.** The AWS server never imports from the
Google Workspace server or the GitHub server, and vice versa. Each
server is self-contained except for shared utilities.

**Read-only verification.** Before implementing any tool, verify that
the underlying API call is genuinely read-only. Check the HTTP method
(must be GET or POST for read operations like CloudTrail LookupEvents),
the IAM permission required (must be a read/list/describe permission,
never a write/create/delete/update permission), and the API documentation
confirmation that the call does not modify state.

**Credential lifecycle.** Create the authenticated client at the start
of the tool execution, use it for the API calls, and let it go out of
scope at the end. Never assign credentials to module-level variables,
class attributes, or any structure that persists beyond the single
invocation.

**Pagination completeness.** When a tool declares pagination support,
the implementation must fetch ALL pages by default. Never return partial
results from a paginated API without following the pagination cursor to
completion. The only exception is if the invocation times out, in which
case return what was collected with status `"partial"`.

**Data hash computation.** After assembling the response data, compute
the SHA-256 hash of the JSON-serialized data and include it in the
response metadata. This hash is what appears in the transparency log
and allows users to verify data integrity.