"""Step 12.3 trace/metric contracts; model clients are scripted doubles."""
import asyncio
import os
from types import SimpleNamespace
from uuid import uuid4
import pytest


def test_runtime_propagates_trace_but_not_database_credentials(monkeypatch):
    from scripts.runtime import runtime_environment
    parent='00-'+'1'*32+'-'+'2'*16+'-01'
    monkeypatch.setenv('TRACEPARENT',parent)
    monkeypatch.setenv('OTEL_EXPORTER_OTLP_ENDPOINT','http://collector:4318')
    monkeypatch.setenv('AGENT_DB_PASSWORD','must-not-cross-boundary')
    env=runtime_environment()
    assert env['TRACEPARENT']==parent
    assert env['OTEL_EXPORTER_OTLP_ENDPOINT']=='http://collector:4318'
    assert 'AGENT_DB_PASSWORD' not in env


@pytest.fixture
def spans(monkeypatch):
    import telemetry
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    exporter=InMemorySpanExporter();provider=TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(telemetry,'_providers',{key:provider for key in ['api','worker','agent','mcp']})
    yield exporter
    provider.shutdown()


def test_model_step_and_tool_spans_preserve_trace_without_content(spans):
    import telemetry
    from tests.test_agent import run,completion,FINAL
    with telemetry.span('task.create','api') as root:
        outcome,*_=run([completion([('run_sql',{'sql':'secret SQL'})]),completion([FINAL])])
    assert outcome.termination=='final_answer'
    ended=spans.get_finished_spans()
    assert len({s.context.trace_id for s in ended})==1
    assert sum(s.name=='agent.step' for s in ended)==2
    models=[s for s in ended if s.attributes.get('gen_ai.operation.name')=='chat']
    assert len(models)==2
    assert models[0].attributes['gen_ai.request.model']=='test'
    assert models[0].attributes['gen_ai.usage.input_tokens']==9
    assert models[0].attributes['gen_ai.usage.output_tokens']==1
    assert any(s.attributes.get('gen_ai.tool.name')=='run_sql' for s in ended)
    assert 'secret SQL' not in str([dict(s.attributes) for s in ended])


def test_retry_span_covers_attempts_and_wait_without_error_text(spans):
    from tests.test_runtime_hardening import client_for,status_error
    from tests.test_agent import completion,FINAL
    from agent.model import request
    client,_=client_for([status_error(503,'private error'),completion([FINAL])])
    async def sleep(_):pass
    asyncio.run(request(client,'fixture',[],lambda *a:None,sleep=sleep))
    models=[s for s in spans.get_finished_spans() if s.attributes.get('gen_ai.operation.name')=='chat']
    assert len(models)==1
    assert models[0].attributes['retry_count']==1
    assert models[0].attributes['retry_wait_ms']>=0
    assert models[0].events[0].attributes['error_class']=='retryable'
    assert 'private error' not in str(models[0].attributes)+str(models[0].events)


def test_cached_usage_cost_and_missing_cache_are_distinct(monkeypatch):
    from telemetry import usage_summary
    import config
    monkeypatch.setattr(config,'TOKEN_PRICE_INPUT',2.0)
    monkeypatch.setattr(config,'TOKEN_PRICE_CACHED_INPUT',0.5)
    monkeypatch.setattr(config,'TOKEN_PRICE_OUTPUT',3.0)
    value=usage_summary({'prompt_tokens':100,'completion_tokens':20,'prompt_cache_hit_tokens':40})
    assert value['cached_tokens']==40 and value['cache_hit_ratio']==.4
    assert value['cost_yuan']==pytest.approx(.0002)
    unknown=usage_summary({'prompt_tokens':100,'completion_tokens':20})
    assert unknown['cached_tokens'] is None and unknown['cost_yuan'] is None


def test_mcp_header_and_server_restore_the_tool_parent(spans):
    import json,httpx,telemetry
    from agent.mcp_client import MCPClient,idempotency_header
    from mcp_olist.server import BearerAuth
    parents=[];metas=[]
    async def call_tool(name,args,meta):
        metas.append(meta)
        return SimpleNamespace(isError=False,structuredContent={'result_id':'fixture','row_count':2,'truncated':False})
    async def app(scope,receive,send):parents.append(telemetry.traceparent())
    async def run():
        remote=MCPClient('http://fixture','local-test-token','task')
        remote.session=SimpleNamespace(call_tool=call_tool)
        with telemetry.span('agent.step','agent'):
            await remote.call('run_sql',{'sql':'private query'})
        request=httpx.Request('POST','http://fixture/mcp',json={'method':'tools/call','params':{'_meta':metas[0]}})
        await idempotency_header(request)
        assert request.headers['traceparent']==metas[0]['traceparent']
        token='scripted-authentication-fixture'
        await BearerAuth(app,token)({'type':'http','path':'/mcp','headers':[(b'authorization',('Bearer '+token).encode()),(b'traceparent',request.headers['traceparent'].encode())]},None,None)
    asyncio.run(run())
    ended=spans.get_finished_spans()
    client=next(s for s in ended if s.name=='mcp.call');server=next(s for s in ended if s.name=='mcp.request')
    assert server.parent.span_id==client.context.span_id
    assert server.context.trace_id==client.context.trace_id
    assert client.attributes['row_count']==2 and client.attributes['truncated'] is False
    assert parents and 'private query' not in str([s.attributes for s in ended])


def test_empty_export_endpoint_never_constructs_exporter(monkeypatch):
    import telemetry,config
    from opentelemetry.exporter.otlp.proto.http import trace_exporter
    monkeypatch.setattr(config,'OTEL_EXPORTER_OTLP_ENDPOINT','')
    monkeypatch.setattr(telemetry,'_providers',{})
    def forbidden(**kwargs):raise AssertionError('export should be disabled')
    monkeypatch.setattr(trace_exporter,'OTLPSpanExporter',forbidden)
    with telemetry.span('disabled-export','agent'):
        assert telemetry.traceparent()
    telemetry.flush()


def test_service_lifespans_flush_pending_spans_before_process_exit(monkeypatch):
    import telemetry
    from fastapi.testclient import TestClient
    from mcp_olist import server
    from mcp.server.fastmcp import FastMCP
    from api.memories import app
    calls=[]
    monkeypatch.setattr(telemetry,'flush',lambda:calls.append('flush'))
    monkeypatch.setenv('AGENT_DB_PASSWORD','local-scripted-secret')
    monkeypatch.setenv('AGENT_RO_PASSWORD','local-scripted-secret')
    monkeypatch.setenv('MCP_BEARER_TOKEN','scripted-authentication-fixture')
    monkeypatch.setenv('MEMORY_API_SECRET','scripted-signing-secret-for-unit-test')
    # SDK session managers have a single lifecycle; do not consume the global
    # production app used by another integration test in this process.
    monkeypatch.setattr(server,'mcp',FastMCP('flush-fixture',stateless_http=True,json_response=True))
    with TestClient(server.create_app(token='scripted-authentication-fixture')):pass
    assert calls==['flush']
    with TestClient(app):pass
    assert calls==['flush','flush']


def test_trace_receipt_waits_for_collector_ingestion(monkeypatch):
    from scripts import step12_trace
    reads=[]
    class Client:
        def __init__(self,**_):pass
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def get(self,*_):
            reads.append(1)
            names={'task.create'} if len(reads)==1 else step12_trace.REQUIRED_SPANS
            return SimpleNamespace(status_code=200,json=lambda:{'data':[{'spans':[{'operationName':name} for name in names]}]})
    monkeypatch.setattr(step12_trace.httpx,'Client',Client)
    monkeypatch.setattr(step12_trace.time,'sleep',lambda *_:None)
    step12_trace.fetch_trace('fixture')
    assert len(reads)==2


@pytest.mark.integration
@pytest.mark.skipif(os.getenv('RUN_DB_TESTS')!='1',reason='local PostgreSQL required')
def test_api_worker_mcp_sql_and_metrics_chain(spans,monkeypatch):
    import psycopg
    from config import db_kwargs
    from api.tasks import create_task,NewTask,app
    from scripts import task_worker as worker
    from mcp_olist.service import run_query
    from contracts import FinalAnswer
    from fastapi.testclient import TestClient
    import telemetry
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        owner=conn.execute('INSERT INTO users(username) VALUES(%s) RETURNING user_id',('trace-'+uuid4().hex,)).fetchone()[0]
    ident=create_task(NewTask(question='trace fixture'),owner)['task_id']
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        stored=conn.execute('SELECT traceparent FROM tasks WHERE task_id=%s',(ident,)).fetchone()[0]
    assert stored.startswith('00-')
    def runtime(question,task_id,emit,**kwargs):
        with telemetry.span('mcp.request','mcp',parent=telemetry.traceparent()):
            result=run_query('SELECT count(*) AS n FROM orders',str(task_id),kwargs['lease_token'])
        assert result['row_count']==1
        emit('model_call',{'usage':{'prompt_tokens':100,'completion_tokens':20,'total_tokens':120,'prompt_cache_hit_tokens':40},'error_class':None},120,25)
        emit('number_gate',{'replaced':['unsupported']})
        emit('termination',{'scope':'task','reason':'final_answer'})
        return FinalAnswer(answer='scripted',claims=[])
    monkeypatch.setattr(worker,'run_runtime',runtime)
    worker.process(worker.claim(ident))
    ended=spans.get_finished_spans()
    names={s.name for s in ended}
    assert {'task.create','worker.claim','worker.execute','mcp.request','sql.execute'}<=names
    assert len({s.context.trace_id for s in ended})==1
    sql_span=next(s for s in ended if s.name=='sql.execute')
    assert set(sql_span.attributes)=={'sql_hash','duration_ms'}
    response=TestClient(app).get('/metrics')
    assert response.status_code==200
    for metric in ['olist_tasks','olist_model_calls_total','olist_tokens_total','olist_model_duration_seconds_bucket','olist_sql_duration_seconds_bucket','olist_queue_depth','olist_circuit_state','olist_lease_takeovers_total','olist_gate_replacements_total']:
        assert metric in response.text
    assert 'task_id=' not in response.text and 'user_id=' not in response.text and 'sql=' not in response.text
