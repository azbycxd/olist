"""Infrastructure recovery uses the existing shared fault-requeue budget."""
import asyncio
import os
from types import SimpleNamespace
from uuid import uuid4
import httpx
import pytest


def test_mcp_timeout_is_not_swallowed_as_a_model_tool_error():
    from agent.tools import Registry
    from agent.infra import InfraRetryable
    class Remote:
        tools=[{'function':{'name':'list_tables'}}]
        async def call(self,*_):raise InfraRetryable('timeout')
    with pytest.raises(InfraRetryable):asyncio.run(Registry(Remote(),lambda *a:None).call('list_tables',{},'boot'))


def test_classification_is_narrow_and_unwraps_exception_groups():
    from agent.infra import retryable_exception
    from mcp.shared.exceptions import McpError
    from mcp.types import ErrorData
    assert retryable_exception(httpx.ConnectError('fixture'))
    assert retryable_exception(ExceptionGroup('transport',[TimeoutError('fixture')]))
    assert retryable_exception(McpError(ErrorData(code=408,message='Timed out while waiting for response to ClientRequest. Waited 30.0 seconds.')))
    assert not retryable_exception(McpError(ErrorData(code=-32001,message='Unrecognized server application error')))
    assert not retryable_exception(PermissionError('denied'))
    assert not retryable_exception(ValueError('SQL syntax error'))
    assert not retryable_exception(ExceptionGroup('mixed',[TimeoutError(),PermissionError()]))
    assert not retryable_exception(McpError(ErrorData(code=-32602,message='invalid SQL parameters')))


@pytest.mark.parametrize('code',['unknown_dimension','forbidden_dimension','syntax_error','permission_denied','fatal'])
def test_semantic_and_permission_results_do_not_requeue(code):
    from agent.mcp_client import MCPClient
    async def call(*a,**k):return SimpleNamespace(isError=False,structuredContent={'error':code})
    remote=MCPClient('http://fixture','scripted-token','task')
    remote.session=SimpleNamespace(call_tool=call)
    assert asyncio.run(remote.call('run_sql',{'sql':'fixture'}))=={'error':code}


@pytest.mark.integration
@pytest.mark.skipif(os.getenv('RUN_DB_TESTS')!='1',reason='local database required')
@pytest.mark.parametrize('failures,expected,requeues',[(2,'completed',2),(100,'failed',3)])
def test_bootstrap_failure_recovery_and_shared_limit(monkeypatch,failures,expected,requeues):
    import psycopg
    from config import db_kwargs
    from api.tasks import create_task,NewTask
    from scripts import task_worker as worker
    from contracts import FinalAnswer
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        owner=conn.execute("INSERT INTO users(username,data_scope) VALUES(%s,ARRAY['ALL']) RETURNING user_id",('infra-'+uuid4().hex,)).fetchone()[0]
    ident=create_task(NewTask(question='infra scripted bootstrap'),owner)['task_id']
    attempts=[]
    def runtime(question,ident,emit,**kwargs):
        from agent import worker as runtime_worker
        async def bootstrap(_):
            attempts.append(1)
            if len(attempts)<=failures:raise httpx.ConnectError('scripted MCP initialization unavailable')
            emit('termination',{'scope':'task','reason':'final_answer'})
        monkeypatch.setattr(runtime_worker,'_execute',bootstrap)
        monkeypatch.setattr(runtime_worker,'emit',emit)
        asyncio.run(runtime_worker._execute_with_errors({}))
        return FinalAnswer(answer='scripted',claims=[])
    monkeypatch.setattr(worker,'run_runtime',runtime)
    for _ in range(5):
        job=worker.claim(ident)
        if job is None:break
        worker.process(job)
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        status,error,count=conn.execute('SELECT status,error,provider_requeues FROM tasks WHERE task_id=%s',(ident,)).fetchone()
    assert (status,count)==(expected,requeues)
    assert error==(None if expected=='completed' else 'infra_unavailable')


def test_mcp_bootstrap_unavailable_gets_task_termination(monkeypatch,capsys):
    from agent import worker
    async def execute(_):raise httpx.ConnectError('MCP initialization fixture')
    monkeypatch.setattr(worker,'_execute',execute)
    asyncio.run(worker._execute_with_errors({}))
    assert 'infra_retryable' in capsys.readouterr().out


def test_server_database_classification_does_not_retry_sql_or_permissions():
    import psycopg
    from psycopg_pool import PoolTimeout
    from mcp_olist.infra import retryable
    assert retryable(PoolTimeout())
    assert retryable(psycopg.errors.ConnectionFailure())
    assert retryable(psycopg.errors.QueryCanceled())
    assert not retryable(psycopg.errors.SyntaxError())
    assert not retryable(psycopg.errors.InsufficientPrivilege())
    assert not retryable(psycopg.errors.InvalidPassword())


def test_cleanup_error_keeps_the_known_transport_cause():
    from agent.mcp_client import MCPClient
    from agent.infra import InfraRetryable
    async def close(*_):raise RuntimeError('SDK cancellation cleanup fixture')
    remote=MCPClient('http://fixture','scripted-token','task')
    remote.stack=SimpleNamespace(__aexit__=close)
    original=InfraRetryable('MCP request timed out')
    with pytest.raises(InfraRetryable) as caught:asyncio.run(remote.__aexit__(type(original),original,None))
    assert caught.value is original


def test_real_sdk_timeout_uses_http_408_and_is_retryable():
    import anyio
    from datetime import timedelta
    from mcp import ClientSession
    from mcp.shared.exceptions import McpError
    from agent.infra import retryable_exception
    async def expire():
        server_send,client_read=anyio.create_memory_object_stream(1)
        client_send,server_read=anyio.create_memory_object_stream(1)
        async with server_send,client_read,client_send,server_read:
            async with ClientSession(client_read,client_send,read_timeout_seconds=timedelta(milliseconds=10)) as session:
                try:await session.send_ping()
                except McpError as exc:return exc
        raise AssertionError('SDK did not time out')
    exc=asyncio.run(expire())
    assert exc.error.code==httpx.codes.REQUEST_TIMEOUT
    assert retryable_exception(exc)
