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
def test_same_content_in_parallel_reuses_one_result(task):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda statement:service.run_query(statement,task),['select 42 as n','SELECT  42 AS n']))
    assert results[0]['result_id']==results[1]['result_id']
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
