"""Tool-facing error type.

Tools raise LocalCallError instead of returning error payloads, so the MCP
layer marks the CallToolResult with `isError: true` at the protocol level
(per the MCP specification), while the message still carries a stable code
and an actionable hint for the online model.
"""

from __future__ import annotations


class LocalCallError(Exception):
    """One failed local call, with a stable error code."""

    def __init__(self, message: str, code: str) -> None:
        self.message = message
        self.code = code
        prefix = f"[{code}] "
        super().__init__(message if message.startswith(prefix) else prefix + message)
