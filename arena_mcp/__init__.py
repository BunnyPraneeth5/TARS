"""arena_mcp – MCP client wrapper and polling loop for Agent Arena."""

from arena_mcp.client import get_task, submit_task  # noqa: F401
from arena_mcp.poll import run_loop  # noqa: F401
