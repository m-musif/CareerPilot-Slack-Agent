"""
Synchronous wrapper around an MCP stdio client.

Bolt handlers are synchronous, but the MCP Python SDK is async. This module
runs a persistent asyncio event loop in a background thread, keeps one MCP
ClientSession open to the CareerTools server, and exposes simple sync methods
(`list_tools`, `call_tool`) that bridge into that loop.
"""
from __future__ import annotations

import asyncio
import sys
import threading
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_SCRIPT = (
    Path(__file__).resolve().parent.parent / "mcp_server" / "career_tools_server.py"
)


class MCPClient:
    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._ready = threading.Event()
        self._error: Exception | None = None
        self._session: ClientSession | None = None
        self._tools: list = []
        self._stop: asyncio.Event | None = None

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        except Exception as exc:  # noqa: BLE001
            self._error = exc
            self._ready.set()

    async def _main(self) -> None:
        self._stop = asyncio.Event()
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(SERVER_SCRIPT)],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                self._session = session
                resp = await session.list_tools()
                self._tools = list(resp.tools)
                self._ready.set()
                await self._stop.wait()

    def start(self, timeout: float = 30.0) -> "MCPClient":
        self._thread.start()
        if not self._ready.wait(timeout):
            raise RuntimeError("MCP server did not become ready in time")
        if self._error:
            raise self._error
        return self

    def list_tools(self) -> list:
        return self._tools

    def tool_schemas(self) -> list[dict]:
        """MCP tools mapped to OpenAI/Groq function-calling schema."""
        schemas = []
        for t in self._tools:
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": (t.description or "").strip(),
                        "parameters": t.inputSchema
                        or {"type": "object", "properties": {}},
                    },
                }
            )
        return schemas

    def call_tool(self, name: str, arguments: dict, timeout: float = 30.0) -> str:
        if self._session is None:
            raise RuntimeError("MCP session not ready")
        fut = asyncio.run_coroutine_threadsafe(
            self._session.call_tool(name, arguments), self._loop
        )
        result = fut.result(timeout)
        parts = []
        for chunk in result.content:
            text = getattr(chunk, "text", None)
            if text:
                parts.append(text)
        return "\n".join(parts) if parts else "(no output)"

    def stop(self) -> None:
        if self._stop is not None:
            self._loop.call_soon_threadsafe(self._stop.set)
