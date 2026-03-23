"""Bridge between the Qlik MCP server (stdio) and the Bedrock chat UI.

Launches the MCP server as a subprocess, lists its tools, and executes
tool calls on behalf of the Bedrock client.
"""

import asyncio
import json
import os
import sys
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPBridge:
    """Manages a connection to the Qlik MCP server subprocess."""

    def __init__(self, env: dict[str, str]):
        self._env = {**os.environ, **env}
        self._session: ClientSession | None = None
        self._read = None
        self._write = None
        self._cm = None  # context manager for stdio_client
        self._tools_cache: list[dict] | None = None

    async def connect(self) -> None:
        """Start the MCP server subprocess and establish a session."""
        server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "qlik_sense_mcp_server.server"],
            env=self._env,
        )
        self._cm = stdio_client(server_params)
        self._read, self._write = await self._cm.__aenter__()
        self._session = ClientSession(self._read, self._write)
        await self._session.__aenter__()
        await self._session.initialize()

    async def disconnect(self) -> None:
        """Shut down the MCP session and subprocess."""
        if self._session:
            await self._session.__aexit__(None, None, None)
            self._session = None
        if self._cm:
            await self._cm.__aexit__(None, None, None)
            self._cm = None

    async def list_tools(self) -> list[dict]:
        """List MCP tools and return them in Claude tool_use format."""
        if self._tools_cache is not None:
            return self._tools_cache

        result = await self._session.list_tools()
        tools = []
        for tool in result.tools:
            schema = tool.inputSchema or {"type": "object", "properties": {}}
            # Remove unsupported top-level keys for Claude API
            clean_schema = {
                "type": schema.get("type", "object"),
                "properties": schema.get("properties", {}),
            }
            if "required" in schema:
                clean_schema["required"] = schema["required"]
            tools.append({
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": clean_schema,
            })
        self._tools_cache = tools
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Execute an MCP tool call and return the result as text."""
        result = await self._session.call_tool(name, arguments)
        parts = []
        for content in result.content:
            if hasattr(content, "text"):
                parts.append(content.text)
            else:
                parts.append(str(content))
        return "\n".join(parts)
