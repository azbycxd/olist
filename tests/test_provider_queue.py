"""Queue recovery contracts with local PostgreSQL and scripted runtimes."""
import os
from uuid import uuid4
import psycopg
import pytest
from config import db_kwargs
from scripts import task_worker as worker,provider_health
from contracts import FinalAnswer
from test_task_controls import new

pytestmark=[pytest.mark.integration,pytest.mark.skipif(os.getenv('RUN_DB_TESTS')!='1',reason='local DB required')]


@pytest.fixture
def queued(monkeypatch):
    model='queue-'+uuid4().hex
    monkeypatch.setenv('OPENAI_MODEL',model)
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        owner=conn.execute('INSERT INTO users(username) VALUES(%s) RETURNING user_id',(model,)).fetchone()[0]
    ident=new(owner)
    yield ident,model
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        conn.execute("UPDATE tasks SET status='canceled',lease_token=NULL,lease_expires_at=NULL WHERE task_id=%s",(ident,))


def test_open_provider_leaves_task_unclaimed_but_deadline_still_expires(queued):
    ident,model=queued
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        conn.execute("INSERT INTO provider_health(provider,model,state,open_until) VALUES(%s,%s,'open',clock_timestamp()+interval '30 seconds')",(provider_health.provider_key(),model))
    assert worker.claim(ident) is None
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        assert conn.execute('SELECT status,claim_count FROM tasks WHERE task_id=%s',(ident,)).fetchone()==('pending',0)
        conn.execute("UPDATE tasks SET deadline_at=clock_timestamp()-interval '1 second' WHERE task_id=%s",(ident,))
    assert worker.claim(ident) is None
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        assert conn.execute('SELECT status,error FROM tasks WHERE task_id=%s',(ident,)).fetchone()==('failed','task_timeout')


@pytest.mark.parametrize('reason',['provider_unavailable','model_error'])
def test_running_provider_failures_requeue_without_consuming_claim_budget(queued,monkeypatch,reason):
    ident,_=queued
    def runtime(question,task_id,emit,**kwargs):
        emit('model_call',{'error_class':'retryable','error':'HTTP503'})
        emit('termination',{'scope':'task','reason':reason})
        return FinalAnswer(answer='fixture',claims=[])
    monkeypatch.setattr(worker,'run_runtime',runtime)
    for _ in range(5):
        job=worker.claim(ident)
        assert job is not None
        worker.process(job)
        with psycopg.connect(**db_kwargs('agent','app')) as conn:
            assert conn.execute('SELECT status FROM tasks WHERE task_id=%s',(ident,)).fetchone()[0]=='pending'
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        assert conn.execute('SELECT claim_count-provider_requeues-released_count FROM tasks WHERE task_id=%s',(ident,)).fetchone()[0]==0


def test_unknown_model_error_is_not_requeued(queued,monkeypatch):
    ident,_=queued
    def runtime(question,task_id,emit,**kwargs):
        emit('model_call',{'error_class':'unknown','error':'ValueError'})
        emit('termination',{'scope':'task','reason':'model_error'})
        return FinalAnswer(answer='fixture',claims=[])
    monkeypatch.setattr(worker,'run_runtime',runtime)
    worker.process(worker.claim(ident))
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        assert conn.execute('SELECT status,error FROM tasks WHERE task_id=%s',(ident,)).fetchone()==('failed','model_error')
