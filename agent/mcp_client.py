"""A thin protocol client: discover schemas, forward calls, interpret MCP errors."""

from contextlib import AsyncExitStack
from datetime import timedelta
import json

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


class MCPClient:
    def __init__(self, url, token, task_id):
        self.url, self.token, self.task_id = url, token, task_id
        self.stack = AsyncExitStack()

    async def __aenter__(self):
        try:
            http = await self.stack.enter_async_context(httpx.AsyncClient(
                headers={"Authorization":"Bearer "+self.token, "X-Task-ID":self.task_id}, timeout=30))
            transport = await self.stack.enter_async_context(streamable_http_client(self.url, http_client=http))
            self.session = await self.stack.enter_async_context(ClientSession(transport[0], transport[1],
                                                                 read_timeout_seconds=timedelta(seconds=30)))
            await self.session.initialize()
            self.tools = []
            cursor = None
            while True:
                page = await self.session.list_tools(cursor=cursor)
                self.tools.extend({"type":"function", "function":{"name":t.name,
                    "description":t.description or "", "parameters":t.inputSchema}} for t in page.tools)
                cursor = page.nextCursor
                if not cursor:
                    break
            return self
        except BaseException:
            await self.stack.aclose()
            raise

    async def __aexit__(self, *args):
        return await self.stack.__aexit__(*args)

    async def call(self, name, arguments):
        result = await self.session.call_tool(name, arguments)
        if result.isError:
            return {"error":"mcp_tool_error", "detail":"\n".join(c.text for c in result.content if c.type == "text")[:2000]}
        if result.structuredContent is not None:
            return result.structuredContent
        if len(result.content) == 1 and result.content[0].type == "text":
            try:
                parsed = json.loads(result.content[0].text)
                if isinstance(parsed, dict):
                    return parsed
            except ValueError:
                pass
        return {"content":[c.model_dump(mode="json") for c in result.content]}
