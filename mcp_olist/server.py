"""Official MCP v1 SDK Streamable HTTP server with service Bearer authentication."""

import asyncio
import hmac
import os

import uvicorn
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse

from config import MCP_BEARER_TOKEN
from mcp_olist.catalog import TABLES
from mcp_olist.service import describe, run_query

mcp = FastMCP("olist-readonly", stateless_http=True, json_response=True,
              transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True,
                  allowed_hosts=["localhost:*", "127.0.0.1:*", "mcp-olist:*"],
                  allowed_origins=["http://localhost:*", "http://127.0.0.1:*"]))


@mcp.tool()
def list_tables() -> dict:
    """List available business tables and structural descriptions."""
    return {"tables":[{"name":name, "description":description} for name,description in TABLES.items()]}


@mcp.tool()
async def describe_table(name: str) -> dict:
    """Return column types, database comments and three UNTRUSTED sample rows."""
    return await asyncio.to_thread(describe, name)


@mcp.tool()
async def run_sql(sql: str, ctx: Context) -> dict:
    """Execute one read-only PostgreSQL SELECT; save the capped full result and return its evidence ID."""
    request = ctx.request_context.request
    return await asyncio.to_thread(run_query, sql, request.headers.get("x-task-id", ""))


class BearerAuth:
    def __init__(self, app, token):
        if len(token) < 24:
            raise ValueError("MCP_BEARER_TOKEN must contain at least 24 characters")
        self.app, self.token = app, token

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope["headers"])
            actual = headers.get(b"authorization", b"")
            if not hmac.compare_digest(actual, ("Bearer "+self.token).encode()):
                await JSONResponse({"error":"unauthorized"}, status_code=401,
                                   headers={"WWW-Authenticate":"Bearer"})(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_app(token=MCP_BEARER_TOKEN):
    return BearerAuth(mcp.streamable_http_app(), token)


if __name__ == "__main__":
    uvicorn.run(create_app(), host="0.0.0.0", port=int(os.getenv("MCP_PORT", "8001")), access_log=False)
