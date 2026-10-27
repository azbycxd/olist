"""Fallback acceptance uses fake clients and the real local circuit ledger."""
import asyncio
import os
from types import SimpleNamespace
from uuid import uuid4
import pytest


def configured(monkeypatch):
    monkeypatch.setenv('FALLBACK_BASE_URL','http://fallback.fixture/v1')
    monkeypatch.setenv('FALLBACK_MODEL','fallback-fixture')
    monkeypatch.setenv('FALLBACK_API_KEY','scripted-fallback-key-not-a-real-secret')


def test_parent_switch_routes_to_fallback_and_drops_vendor_fields(monkeypatch):
    import agent.model as model
    from agent.task_control import CONTROL
    from test_agent import completion
    configured(monkeypatch);primary=[];alternate=[];events=[]
    async def create_primary(**kw):primary.append(kw);return completion([])
    async def create_fallback(**kw):alternate.append(kw);return completion([])
    class Alternate:
        def __init__(self,**kw):self.chat=SimpleNamespace(completions=SimpleNamespace(create=create_fallback))
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
    monkeypatch.setattr(model,'AsyncOpenAI',Alternate,raising=False)
    async def admit(payload):return {'route':'fallback','model':'fallback-fixture','remaining_seconds':100}
    async def run():
        token=CONTROL.set(admit)
        try:return await model.request(SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create_primary))),
                'primary',[{'role':'assistant','content':'hello','reasoning_content':'vendor private','vendor_field':'remove'}],
                lambda kind,payload,*_:events.append((kind,payload)))
        finally:CONTROL.reset(token)
    asyncio.run(run())
    assert not primary and len(alternate)==1
    assert alternate[0]['model']=='fallback-fixture' and 'extra_body' not in alternate[0]
    assert alternate[0]['messages']==[{'role':'assistant','content':'hello'}]
    assert next(p for kind,p in events if kind=='model_call')['requested_model']=='fallback-fixture'


@pytest.mark.integration
@pytest.mark.skipif(os.getenv('RUN_DB_TESTS')!='1',reason='local circuit ledger required')
def test_open_primary_switches_and_both_open_are_unavailable(monkeypatch):
    import psycopg
    from config import db_kwargs
    from scripts import provider_health,task_limits,task_worker
    from api.tasks import create_task,NewTask
    from test_runtime_hardening import open_circuit
    configured(monkeypatch)
    primary='primary-'+uuid4().hex;fallback='fallback-'+uuid4().hex
    monkeypatch.setenv('OPENAI_MODEL',primary);monkeypatch.setenv('FALLBACK_MODEL',fallback)
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        owner=conn.execute("INSERT INTO users(username) VALUES(%s) RETURNING user_id",('fallback-'+uuid4().hex,)).fetchone()[0]
    task=create_task(NewTask(question='fallback fixture'),owner)['task_id'];job=task_worker.claim(task)
    try:
        open_circuit(job,primary)
        with psycopg.connect(**db_kwargs('agent','app')) as conn:
            assert provider_health.queue_delay(conn)==0
            call=str(uuid4())
            admission=task_limits.reserve(conn,job['task_id'],job['token'],{'call_id':call,'reserved_tokens':100,'requested_model':primary})
            assert admission['route']=='fallback' and admission['model']==fallback
            assert conn.execute('SELECT provider,model FROM model_reservations WHERE call_id=%s',(call,)).fetchone()==('http://fallback.fixture/v1',fallback)
            conn.execute("UPDATE provider_health SET state='open',open_until=clock_timestamp()+interval '30 seconds' WHERE provider='http://fallback.fixture/v1' AND model=%s",(fallback,))
        with psycopg.connect(**db_kwargs('agent','app')) as conn:
            assert provider_health.queue_delay(conn)>0
            with pytest.raises(task_limits.TaskStopped,match='provider_unavailable'):
                task_limits.reserve(conn,job['task_id'],job['token'],{'call_id':str(uuid4()),'reserved_tokens':100,'requested_model':primary})
    finally:
        with psycopg.connect(**db_kwargs('agent','app')) as conn:task_limits.stop_task(conn,job['task_id'],'canceled')
