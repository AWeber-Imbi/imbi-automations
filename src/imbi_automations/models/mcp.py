"""MCP (Model Context Protocol) server configuration models.

Defines Pydantic models for configuring MCP servers in workflows,
supporting stdio, SSE, and HTTP transport types as supported by
the Claude Agent SDK.
"""

import typing

import pydantic


class McpStdioServer(pydantic.BaseModel):
    """stdio MCP server configuration.

    Launches an MCP server as a subprocess communicating via stdin/stdout.

    Example:
        [mcp_servers.my-postgres]
        type = "stdio"
        command = "uvx"
        args = ["mcp-server-postgres", "postgresql://host/db"]
        env = { DATABASE_URL = "postgresql://..." }
    """

    type: typing.Literal['stdio'] = 'stdio'
    command: str
    args: list[str] = []
    env: dict[str, str] = {}


class McpSSEServer(pydantic.BaseModel):
    """SSE (Server-Sent Events) MCP server configuration.

    Connects to an MCP server over HTTP using Server-Sent Events.

    Example:
        [mcp_servers.my-sse-server]
        type = "sse"
        url = "https://api.example.com/mcp/sse"
        headers = { Authorization = "Bearer token" }
    """

    type: typing.Literal['sse']
    url: str
    headers: dict[str, str] = {}


class McpHttpServer(pydantic.BaseModel):
    """HTTP MCP server configuration.

    Connects to an MCP server over HTTP.

    Example:
        [mcp_servers.my-http-server]
        type = "http"
        url = "https://api.example.com/mcp"
        headers = { Authorization = "Bearer token" }
    """

    type: typing.Literal['http']
    url: str
    headers: dict[str, str] = {}


McpServerConfig = typing.Annotated[
    McpStdioServer | McpSSEServer | McpHttpServer,
    pydantic.Field(discriminator='type'),
]
"""Union type for MCP server configurations with discriminated union."""
