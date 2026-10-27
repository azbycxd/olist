"""A thin protocol client: discover schemas, forward calls, interpret MCP errors."""

from contextlib import AsyncExitStack
from datetime import timedelta
import json
import hashlib
from time import perf_counter
from uuid import uuid4
from agent.call_context import TOOL_CALL_ID,MCP_ROLE
from config import MCP_RETRY_ATTEMPTS
from agent.infra import InfraRetryable,retryable_exception

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


class RetryTransport(httpx.AsyncBaseTransport):
    """Replay one keyed HTTP request on transport failure, including JSON body timeouts."""
    def __init__(self, inner=None):
        self.inner=inner or httpx.AsyncHTTPTransport(retries=0)

    async def handle_async_request(self, request):
        attempts=1+MCP_RETRY_ATTEMPTS if request.headers.get('Idempotency-Key') else 1
        body=await request.aread()
        for attempt in range(attempts):
            response=None
            try:
                request.stream=httpx.ByteStream(body)
                response=await self.inner.handle_async_request(request)
                if request.headers.get('Idempotency-Key') and 'application/json' in response.headers.get('content-type',''):
                    await response.aread()
                return response
            except (httpx.NetworkError,httpx.TimeoutException):
                if response is not None: await response.aclose()
                if attempt+1==attempts: raise

    async def aclose(self):
        await self.inner.aclose()


async def idempotency_header(request):
    if request.method!='POST': return
    try: body=json.loads(await request.aread())
    except (ValueError,TypeError): return
    if body.get('method')=='tools/call':
        key=body.get('params',{}).get('_meta',{}).get('idempotency_key')
        if key: request.headers['Idempotency-Key']=key
        parent=body.get('params',{}).get('_meta',{}).get('traceparent')
        if parent: request.headers['traceparent']=parent


class MCPClient:
    def __init__(self, url, token, task_id, emit=None, lease_token=None,role_tokens=None):
        self.url, self.token, self.task_id = url, token, task_id
        self.lease_token = lease_token
        self.emit = emit
        self.stack = AsyncExitStack()
        self.role_tokens=role_tokens or {}
        self.default_role='agent' if 'agent' in self.role_tokens else 'orchestrator'

    async def request_headers(self,request):
        await idempotency_header(request)
        if not self.role_tokens:return
        role=self.default_role
        if request.method=='POST':
            try:
                body=json.loads(await request.aread())
                role=body.get('params',{}).get('_meta',{}).get('mcp_role',role)
            except (ValueError,TypeError):pass
        request.headers['Authorization']='Bearer '+self.role_tokens[role]

    async def __aenter__(self):
        try:
            http = await self.stack.enter_async_context(httpx.AsyncClient(
                headers={"Authorization":"Bearer "+self.token, "X-Task-ID":self.task_id, **({"X-Lease-Token":self.lease_token} if self.lease_token else {})}, timeout=30,
                transport=RetryTransport(),event_hooks={'request':[self.request_headers]}))
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
        except BaseException as exc:
            try:await self.stack.aclose()
            finally:
                if retryable_exception(exc):raise InfraRetryable(type(exc).__name__) from exc
            raise

    async def __aexit__(self, *args):
        try:return await self.stack.__aexit__(*args)
        except BaseException:
            # SDK cancellation cleanup must not erase the known transport cause.
            if args[1] is not None and retryable_exception(args[1]):raise args[1]
            raise

    async def _observed_call(self, name, arguments, tool_call_id=None):
        ident=tool_call_id or TOOL_CALL_ID.get() or str(uuid4())
        started=perf_counter()
        def summary(value):
            body=json.dumps(value,ensure_ascii=False,sort_keys=True,default=str)
            return {'keys':sorted(value) if isinstance(value,dict) else [],'characters':len(body),
                    'sha256':hashlib.sha256(body.encode()).hexdigest()}
        if self.emit:
            state_payload=arguments.get('payload')
            self.emit('mcp_call',{'call_id':ident,'name':name,'input_summary':summary(arguments),
                'state_role':arguments.get('role') if name=='state_write' else None,
                'subtask_id':state_payload.get('id') if name=='state_write' and isinstance(state_payload,dict) else None})
        try:
            result=await self._call(name,arguments,self.task_id+':'+ident)
        except Exception as exc:
            if self.emit:self.emit('mcp_result',{'call_id':ident,'name':name,'error':type(exc).__name__},0,(perf_counter()-started)*1000)
            if retryable_exception(exc):raise InfraRetryable(type(exc).__name__) from exc
            raise
        if self.emit:
            self.emit('mcp_result',{'call_id':ident,'name':name,'output_summary':summary(result),
                'result_id':result.get('result_id'),'error':result.get('error')},0,(perf_counter()-started)*1000)
        return result

    async def _call(self, name, arguments, key):
        import telemetry
        role=MCP_ROLE.get() or self.default_role
        if self.role_tokens and role not in self.role_tokens:raise PermissionError('MCP role token unavailable')
        result = await self.session.call_tool(name, arguments,meta={'idempotency_key':key,**({'mcp_role':role} if self.role_tokens else {}),**({'traceparent':parent} if (parent:=telemetry.traceparent()) else {})})
        if result.isError:
            return {"error":"mcp_tool_error", "detail":"\n".join(c.text for c in result.content if c.type == "text")[:2000]}
        if result.structuredContent is not None:
            if result.structuredContent.get('error')=='infra_retryable':raise InfraRetryable('MCP infrastructure unavailable')
            return result.structuredContent
        if len(result.content) == 1 and result.content[0].type == "text":
            try:
                parsed = json.loads(result.content[0].text)
                if isinstance(parsed, dict):
                    if parsed.get('error')=='infra_retryable':raise InfraRetryable('MCP infrastructure unavailable')
                    return parsed
            except ValueError:
                pass
        return {"content":[c.model_dump(mode="json") for c in result.content]}


    async def call(self,name,arguments,tool_call_id=None):
        import telemetry
        from opentelemetry.trace import SpanKind
        with telemetry.span('mcp.call','agent',kind=SpanKind.CLIENT,attributes={'gen_ai.tool.name':name}) as current:
            result=await self._observed_call(name,arguments,tool_call_id)
            current.set_attributes(telemetry.tool_attributes(result))
            return result
