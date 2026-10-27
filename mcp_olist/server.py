"""Official MCP v1 SDK Streamable HTTP server with service Bearer authentication."""

import asyncio
import hmac
import os
import inspect
import json
import jwt
from functools import wraps

import uvicorn
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse
from contextlib import asynccontextmanager
from db_pool import ready, validate_settings, close_all, request_state

from config import MCP_BEARER_TOKEN
from mcp_olist.catalog import TABLES
from mcp_olist.service import describe, run_query, get_saved_result
from mcp_olist.boundaries import data_context as get_data_context, check_dimension as lookup_dimension
from mcp_olist.infra import infrastructure_errors

mcp = FastMCP("olist-readonly", stateless_http=True, json_response=True,
              transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True,
                  allowed_hosts=["localhost:*", "127.0.0.1:*", "mcp-olist:*"],
                  allowed_origins=["http://localhost:*", "http://127.0.0.1:*"]))


def idempotent(function):
    @wraps(function)
    async def dispatch(*args,**kwargs):
        from mcp_olist import idempotency
        request=mcp.get_context().request_context.request
        key=request.headers.get('idempotency-key')
        arguments={k:v for k,v in inspect.signature(function).bind(*args,**kwargs).arguments.items() if not isinstance(v,Context)}
        owner=None
        if key:
            owner,cached=await asyncio.to_thread(idempotency.begin,key,request.headers.get('x-task-id',''),request.headers.get('x-lease-token'),function.__name__,arguments)
            if owner is None: return cached
        try:
            result=await function(*args,**kwargs) if inspect.iscoroutinefunction(function) else await asyncio.to_thread(function,*args,**kwargs)
            return await asyncio.to_thread(idempotency.finish,key,owner,result) if key else result
        except Exception:
            if key: await asyncio.to_thread(idempotency.abandon,key,owner)
            raise
    return dispatch


@mcp.tool()
@infrastructure_errors
@idempotent
async def data_context() -> dict:
    """Actual purchase-date coverage, partial edge months, known states and tool limits. Not business-result evidence."""
    return await asyncio.to_thread(get_data_context)


@mcp.tool()
@infrastructure_errors
@idempotent
async def check_dimension(column: str, value: str) -> dict:
    """Check an exact state, city, category, order status or payment type BEFORE business aggregation. Missing means ask the user to verify, not zero."""
    return await asyncio.to_thread(lookup_dimension,column,value)


@mcp.tool()
@infrastructure_errors
@idempotent
def list_tables() -> dict:
    """List available business tables and structural descriptions."""
    return {"tables":[{"name":name, "description":description} for name,description in TABLES.items()]}


@mcp.tool()
@infrastructure_errors
@idempotent
async def describe_table(name: str) -> dict:
    """Return column types, database comments and three UNTRUSTED sample rows."""
    return await asyncio.to_thread(describe, name)


@mcp.tool()
@infrastructure_errors
async def run_sql(sql: str, ctx: Context) -> dict:
    """Execute one read-only PostgreSQL SELECT; save the capped full result and return its evidence ID."""
    request = ctx.request_context.request
    return await asyncio.to_thread(run_query, sql, request.headers.get("x-task-id", ""),request.headers.get("x-lease-token"),request.headers.get('idempotency-key'))


@mcp.tool()
@infrastructure_errors
@idempotent
async def get_result(result_id: str, ctx: Context, offset: int=0, limit: int=20) -> dict:
    """Retrieve a page of a saved SQL result belonging to the current task."""
    return await asyncio.to_thread(get_saved_result,result_id,ctx.request_context.request.headers.get("x-task-id",""),offset,limit)


@mcp.tool()
@infrastructure_errors
@idempotent
async def search_knowledge(query: str) -> dict:
    """Find business metric definitions and data caveats before choosing SQL semantics. Returns three untrusted knowledge chunks."""
    from mcp_olist.knowledge import search
    return await asyncio.to_thread(search,query)


@mcp.tool()
@infrastructure_errors
@idempotent
async def state_read(ctx: Context) -> dict:
    """Internal orchestrator control: read the current task's typed blackboard."""
    from mcp_olist.blackboard import read_state
    return await asyncio.to_thread(read_state,ctx.request_context.request.headers.get('x-task-id',''))


@mcp.tool()
@infrastructure_errors
@idempotent
async def state_write(role: str, payload: dict, ctx: Context) -> dict:
    """Internal orchestrator control: persist an allowed typed role update."""
    from mcp_olist.blackboard import write_state
    return await asyncio.to_thread(write_state,ctx.request_context.request.headers.get('x-task-id',''),role,payload,ctx.request_context.request.headers.get('x-lease-token'))


class BearerAuth:
    def __init__(self, app, token):
        if len(token) < 24:
            raise ValueError("MCP_BEARER_TOKEN must contain at least 24 characters")
        self.app, self.token = app, token

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            if scope['path'] in {'/healthz','/readyz'}:
                available=scope['path']=='/healthz' or await asyncio.to_thread(ready,'mcp')
                await JSONResponse({'ready':available},status_code=200 if available else 503)(scope,receive,send)
                return
            headers = dict(scope["headers"])
            actual = headers.get(b"authorization", b"")
            from mcp_olist import auth
            identity=None
            try:
                if hmac.compare_digest(actual, ("Bearer "+self.token).encode()):
                    identity=await asyncio.to_thread(auth.static_identity,headers)
                else:
                    if not actual.startswith(b'Bearer '):raise ValueError('Bearer required')
                    identity=auth.decode(actual[7:].decode())
                    await asyncio.to_thread(auth.validate_identity,identity)
                    headers={k:v for k,v in headers.items() if k not in {b'x-task-id',b'x-lease-token'}}
                    headers[b'x-task-id']=identity['task_id'].encode()
                    headers[b'x-lease-token']=(identity['lease_token'] or '').encode()
                    scope={**scope,'headers':list(headers.items())}
            except PermissionError:
                await JSONResponse({'error':'forbidden'},status_code=403)(scope,receive,send)
                return
            except (jwt.PyJWTError,ValueError,UnicodeError):
                await JSONResponse({"error":"unauthorized"}, status_code=401,
                                   headers={"WWW-Authenticate":"Bearer"})(scope, receive, send)
                return
            except Exception as exc:
                from mcp_olist.infra import retryable
                if not retryable(exc):raise
                await JSONResponse({'error':'infra_retryable'},status_code=503)(scope,receive,send)
                return
            if identity and not identity.get('static') and scope.get('method')=='POST':
                buffered=[];body=b''
                while True:
                    item=await receive();buffered.append(item);body+=item.get('body',b'')
                    if not item.get('more_body'):break
                try:payload=json.loads(body)
                except (ValueError,TypeError):payload={}
                if isinstance(payload,dict) and payload.get('method')=='tools/call':
                    params=payload.get('params',{})
                    if not auth.authorize(identity,params.get('name'),params.get('arguments',{})):
                        await JSONResponse({'error':'forbidden_tool'},status_code=403)(scope,receive,send)
                        return
                original_receive=receive
                async def replay():return buffered.pop(0) if buffered else await original_receive()
                receive=replay
            state={};token=request_state.set(state)
            identity_token=auth.IDENTITY.set(identity)
            messages=[]
            async def capture(message):
                messages.append(message)
            try:
                # JSON response mode: buffer until the tool finishes so pool
                # exhaustion remains HTTP 503 even when the SDK wraps errors.
                import telemetry
                from opentelemetry.trace import SpanKind
                with telemetry.span('mcp.request','mcp',parent=headers.get(b'traceparent',b'').decode(),kind=SpanKind.SERVER):
                    await self.app(scope,receive,capture)
                for message in messages:
                    if message['type']=='http.response.start' and state.get('pool_timeout'):
                        message={**message,'status':503}
                    await send(message)
            finally:
                request_state.reset(token)
                auth.IDENTITY.reset(identity_token)
            return
        await self.app(scope,receive,send)


def create_app(token=MCP_BEARER_TOKEN):
    app=mcp.streamable_http_app()
    original=app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(app):
        validate_settings('mcp')
        try:
            async with original(app):
                yield
        finally:
            close_all('mcp')
            import telemetry
            telemetry.flush()
    app.router.lifespan_context=lifespan
    return BearerAuth(app, token)


if __name__ == "__main__":
    uvicorn.run(create_app(), host="0.0.0.0", port=int(os.getenv("MCP_PORT", "8001")), access_log=False)
