"""Step12 A3: SQL execution and retry behavior, using real local DB or fake HTTP."""
import asyncio
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import httpx
import psycopg
import pytest
from config import db_kwargs
from mcp_olist import service

integration=pytest.mark.skipif(os.getenv('RUN_DB_TESTS')!='1',reason='local DB required')


@pytest.fixture
def task():
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        owner=conn.execute('INSERT INTO users(username) VALUES(%s) RETURNING user_id',('idempotency-'+uuid4().hex,)).fetchone()[0]
        ident=conn.execute("INSERT INTO tasks(user_id,question,status) VALUES(%s,'SQL retry fixture','running') RETURNING task_id",(owner,)).fetchone()[0]
    yield str(ident)
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        conn.execute("UPDATE tasks SET status='completed' WHERE task_id=%s",(ident,))


@pytest.mark.integration
@integration
def test_same_transport_key_reuses_exact_response(task):
    key=task+':call-1'
    first=service.run_query('SELECT 42 AS n',task,idempotency_key=key)
    assert service.run_query('SELECT 42 AS n',task,idempotency_key=key)==first
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        assert conn.execute('SELECT count(*) FROM query_results WHERE task_id=%s',(task,)).fetchone()[0]==1


@pytest.mark.integration
@integration
def test_same_content_in_parallel_reuses_one_result(task,monkeypatch):
    original=psycopg.Connection.execute
    executions=[]
    def counted(conn,query,*args,**kwargs):
        if isinstance(query,str) and query.startswith('SELECT 42 AS n LIMIT '): executions.append(query)
        return original(conn,query,*args,**kwargs)
    monkeypatch.setattr(psycopg.Connection,'execute',counted)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda statement:service.run_query(statement,task),['select 42 as n','SELECT  42 AS n']))
    assert results[0]['result_id']==results[1]['result_id']
    assert len(executions)==1
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        assert conn.execute('SELECT count(*) FROM query_results WHERE task_id=%s',(task,)).fetchone()[0]==1


def test_http_connection_retry_preserves_idempotency_header():
    from agent.mcp_client import RetryTransport
    seen=[]
    async def dispatch(request):
        seen.append(request.headers['Idempotency-Key'])
        if len(seen)==1: raise httpx.ReadTimeout('lost fixture response',request=request)
        return httpx.Response(200,json={'ok':True})
    async def run():
        async with httpx.AsyncClient(transport=RetryTransport(httpx.MockTransport(dispatch))) as client:
            return await client.post('http://fixture/mcp',headers={'Idempotency-Key':'task:call'},json={'method':'tools/call'})
    assert asyncio.run(run()).status_code==200
    assert seen==['task:call','task:call']


@pytest.mark.integration
@integration
def test_running_expiry_takeover_conflict_and_stale_completion(task):
    from mcp_olist import idempotency
    key=task+':pending'
    old,_=idempotency.begin(key,task,None,'run_sql',{'sql':'SELECT 42 AS n'})
    assert service.run_query('SELECT 42 AS n',task,idempotency_key=key)['error']=='tool_in_progress'
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        conn.execute("UPDATE tool_calls SET updated_at=clock_timestamp()-interval '30 seconds' WHERE key=%s",(key,))
    result=service.run_query('SELECT 42 AS n',task,idempotency_key=key)
    assert result['result_id']
    assert idempotency.finish(key,old,{'wrong':True})['error']=='tool_in_progress'
    with pytest.raises(ValueError,match='conflicts'):
        service.run_query('SELECT 43 AS n',task,idempotency_key=key)


@pytest.mark.integration
@integration
def test_cached_result_still_requires_active_task(task):
    key=task+':fenced'
    service.run_query('SELECT 42 AS n',task,idempotency_key=key)
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        conn.execute("UPDATE tasks SET status='canceled' WHERE task_id=%s",(task,))
    with pytest.raises(ValueError,match='not active'):
        service.run_query('SELECT 42 AS n',task,idempotency_key=key)


def test_parallel_request_header_uses_each_request_metadata():
    from agent.mcp_client import idempotency_header
    async def run():
        requests=[httpx.Request('POST','http://fixture/mcp',json={'method':'tools/call','params':{'_meta':{'idempotency_key':key}}}) for key in ['a:1','a:2']]
        await asyncio.gather(*(idempotency_header(r) for r in requests))
        return [r.headers['Idempotency-Key'] for r in requests]
    assert asyncio.run(run())==['a:1','a:2']


def test_http_retry_never_retries_a_third_time_or_an_unkeyed_call():
    from agent.mcp_client import RetryTransport
    for keyed,expected in [(True,2),(False,1)]:
        sent=[]
        async def dispatch(request):
            sent.append(True)
            raise httpx.ConnectError('fixture',request=request)
        async def run():
            async with httpx.AsyncClient(transport=RetryTransport(httpx.MockTransport(dispatch))) as client:
                await client.post('http://fixture',headers={'Idempotency-Key':'task:call'} if keyed else {})
        with pytest.raises(httpx.ConnectError): asyncio.run(run())
        assert len(sent)==expected


@pytest.mark.integration
@integration
@pytest.mark.skipif(os.getenv('RUN_MCP_TESTS')!='1',reason='live MCP required')
def test_live_mcp_sends_key_and_replays_original_response(task):
    from agent.mcp_client import MCPClient
    from config import MCP_URL,MCP_BEARER_TOKEN
    async def run():
        async with MCPClient(MCP_URL,MCP_BEARER_TOKEN,task) as client:
            first=await client.call('run_sql',{'sql':'SELECT 42 AS n'},tool_call_id='test-id')
            second=await client.call('run_sql',{'sql':'SELECT 42 AS n'},tool_call_id='test-id')
            assert first==second and first.get('result_id')
            await client.call('list_tables',{},tool_call_id='catalog')
    asyncio.run(run())
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        assert conn.execute("SELECT count(*) FROM tool_calls WHERE task_id=%s AND status='done'",(task,)).fetchone()[0]==2
