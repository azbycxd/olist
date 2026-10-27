"""Narrow transport classification, without importing database drivers in Agent."""
import asyncio
import httpx
import anyio
from mcp.shared.exceptions import McpError


class InfraRetryable(Exception):
    pass


def retryable_exception(exc):
    if isinstance(exc,BaseExceptionGroup):
        meaningful=[e for e in exc.exceptions if not isinstance(e,asyncio.CancelledError)]
        return bool(meaningful) and all(retryable_exception(e) for e in meaningful)
    if isinstance(exc,(InfraRetryable,TimeoutError,ConnectionError,httpx.NetworkError,httpx.TimeoutException,
                       httpx.RemoteProtocolError,anyio.EndOfStream,anyio.BrokenResourceError,anyio.ClosedResourceError)):
        return True
    if isinstance(exc,httpx.HTTPStatusError):return exc.response.status_code in {408,429,500,502,503,504}
    if isinstance(exc,McpError):
        return exc.error.code==-32001  # SDK request timeout, not arbitrary tool text.
    return False
