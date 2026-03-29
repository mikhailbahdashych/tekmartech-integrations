"""Google Workspace MCP server entry point.

Registers the Google Workspace MCP server using the MCP SDK low-level Server API.
All four tools are registered with their definitions and execute functions.
The server communicates over stdio transport.

IMPORTANT: structlog writes to stderr to avoid interfering with the
MCP JSON-RPC messages on stdout.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from typing import Any

import anyio
import structlog
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import TextContent
from mcp.types import Tool as MCPTool

from google_workspace.tools import (
    get_user_mfa_status,
    list_login_events,
    list_user_tokens,
    list_users,
)
from shared.error_formatting import (
    format_internal_error,
    format_validation_error,
    sanitize_error_message,
)
from shared.models import ToolInvocationRequest
from shared.response_builder import build_error_response

# Configure structlog to write to stderr (stdout is reserved for MCP JSON-RPC)
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
)

logger = structlog.get_logger()

TOOLS: dict[str, Any] = {
    "google_workspace.list_users": list_users,
    "google_workspace.get_user_mfa_status": get_user_mfa_status,
    "google_workspace.list_user_tokens": list_user_tokens,
    "google_workspace.list_login_events": list_login_events,
}

server = Server(name="tekmar-google-workspace-mcp")


@server.list_tools()
async def handle_list_tools() -> list[MCPTool]:
    """Return tool definitions for all registered Google Workspace tools."""
    return [
        MCPTool(
            name=tool_module.definition["tool_name"],
            description=tool_module.definition["description"],
            inputSchema=tool_module.definition["input_schema"],
        )
        for tool_module in TOOLS.values()
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle a tool invocation request.

    Args:
        name: The MCP tool name being invoked.
        arguments: The full invocation request as a dict.

    Returns:
        A list containing a single TextContent with the JSON-serialized
        ToolInvocationResponse.
    """
    started_at = datetime.now(UTC)

    try:
        request = ToolInvocationRequest.model_validate(arguments)
    except Exception as exc:
        error_response = build_error_response(
            invocation_id=arguments.get("invocation_id", "unknown"),
            error=format_validation_error(
                f"Invalid invocation request: {sanitize_error_message(str(exc))}"
            ),
            started_at=started_at,
        )
        return [TextContent(type="text", text=error_response.model_dump_json())]

    tool_module = TOOLS.get(name)
    if tool_module is None:
        error_response = build_error_response(
            invocation_id=request.invocation_id,
            error=format_validation_error(f"Unknown tool: {name}"),
            started_at=started_at,
        )
        return [TextContent(type="text", text=error_response.model_dump_json())]

    try:
        result = await tool_module.execute(
            request.parameters,
            request.credentials,
            request.invocation_id,
            request.timeout_seconds,
        )
        return [TextContent(type="text", text=result.model_dump_json())]
    except Exception as exc:
        logger.error(
            "tool_execution_failed",
            module="google_workspace",
            action="call_tool",
            tool_name=name,
            error=sanitize_error_message(str(exc)),
        )
        error_response = build_error_response(
            invocation_id=request.invocation_id,
            error=format_internal_error(sanitize_error_message(str(exc))),
            started_at=started_at,
        )
        return [TextContent(type="text", text=error_response.model_dump_json())]


async def run() -> None:
    """Start the Google Workspace MCP server on stdio transport."""
    logger.info(
        "server_starting",
        module="google_workspace",
        action="startup",
        server_name="tekmar-google-workspace-mcp",
        server_version="0.1.0",
    )
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="tekmar-google-workspace-mcp",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    anyio.run(run)
