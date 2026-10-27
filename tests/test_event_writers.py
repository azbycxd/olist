"""Regression-found event sequence conflict: fake adapter, real SQL/event writers."""
import os
from types import SimpleNamespace
from uuid import uuid4
import pytest

pytestmark=[pytest.mark.integration,pytest.mark.skipif(os.getenv('RUN_DB_TESTS')!='1',reason='local DB required')]


def test_evaluator_and_sql_events_share_atomic_sequence(monkeypatch,tmp_path):
    from eval import run as runner
    from mcp_olist.service import run_query
    from contracts import FinalAnswer
    import logging
    # A synthetic A fixture; no C/D/E workload, model or real scoring.
    q={'id':'synthetic-event-fixture','category':'A','split':'dev','question':'fixture','answer_type':'number','gold_sql':'SELECT 42 AS n'}
    class Fixture:
        name='scripted';version='fixture'
        def run(self,case,emit):
            emit('model_call',{'role':'agent','attempt':0,'usage':{'prompt_tokens':5,'completion_tokens':2,'total_tokens':7}})
            result=run_query('SELECT 42 AS n',case.task_id)
            emit('termination',{'reason':'final_answer','steps':1})
            return FinalAnswer(answer=42,claims=[{'text':'fixture','value':42,'evidence':[result['result_id']]}])
    monkeypatch.setattr(runner,'load_questions',lambda:[q])
    monkeypatch.setattr(runner,'make_adapter',lambda _:Fixture())
    monkeypatch.setattr(runner,'execute_gold',lambda *_:(42,[{'n':42}]))
    monkeypatch.setattr(runner,'score',lambda *_:{'correct':True})
    monkeypatch.setattr(runner,'provenance',lambda **_: {})
    monkeypatch.setattr(runner,'append_results',lambda *_:None)
    monkeypatch.setattr(runner,'write_evidence',lambda name,value:tmp_path/name)
    log=tmp_path/'scripted.jsonl';log.touch()
    logger=logging.getLogger('event-fixture-'+uuid4().hex);logger.addHandler(logging.FileHandler(log))
    monkeypatch.setattr(runner,'start_log',lambda _: (logger,log))
    for key in 'NUMBER_GATE SCHEMA_MODE CONTEXT_STRATEGY CONTEXT_SUMMARY_THRESHOLD CONTEXT_LIMIT RAG_MODE USE_MEMORY AGENT_MODE TOKEN_BUDGET'.split():
        monkeypatch.setenv(key,os.getenv(key,''))
    args=SimpleNamespace(adapter='zero',judge='off',categories=['A'],split='dev',tag='scripted-event-fixture',schema_mode='on_demand',context_strategy='none',context_summary_threshold=6000,context_limit=16000,rag_mode='off',use_memory='false',agent_mode='single',number_gate='false',token_budget=1000)
    result=runner.execute(args)
    assert result['cases'][0]['correct'] and not result['cases'][0].get('error')


def test_autocommit_event_writers_do_not_lose_sequences(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from api.tasks import event
    from config import db_kwargs
    import psycopg
    import time
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        owner=conn.execute('INSERT INTO users(username) VALUES(%s) RETURNING user_id',('event-concurrency-'+uuid4().hex,)).fetchone()[0]
        task=conn.execute("INSERT INTO tasks(user_id,question) VALUES(%s,'synthetic event fixture') RETURNING task_id",(owner,)).fetchone()[0]
    original=psycopg.Connection.execute
    def slow_max(conn,query,*args,**kwargs):
        value=original(conn,query,*args,**kwargs)
        if isinstance(query,str) and query.startswith('SELECT COALESCE(MAX(seq)'):time.sleep(.02)
        return value
    monkeypatch.setattr(psycopg.Connection,'execute',slow_max)
    def write(i):
        with psycopg.connect(**db_kwargs('agent','app'),autocommit=True) as conn:event(conn,task,'fixture',{'i':i})
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(write,range(8)))
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        assert conn.execute('SELECT seq FROM events WHERE task_id=%s ORDER BY seq',(task,)).fetchall()==[(n,) for n in range(1,9)]
