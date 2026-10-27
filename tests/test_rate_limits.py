"""Shared bucket admission and accounting; never contact a real provider."""
import os
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import psycopg
import pytest
from config import db_kwargs
from scripts import task_limits as limits,task_worker as worker
from test_task_controls import new

integration=pytest.mark.skipif(os.getenv('RUN_DB_TESTS')!='1',reason='local PostgreSQL required')


def test_refill_is_fractional_capped_and_never_goes_backwards():
    from scripts.rate_limits import refill
    assert refill(1,10,12)==3
    assert refill(9,10,60)==10
    assert refill(2,10,-10)==2


def test_usage_difference_preserves_unknown_and_overage():
    from scripts.rate_limits import refund_amount
    assert refund_amount(100,{'total_tokens':40})==60
    assert refund_amount(100,{'total_tokens':150})==-50
    assert refund_amount(100,None) is None


def test_rate_limited_runtime_does_not_start_another_memory_model_call(monkeypatch):
    import asyncio
    from agent import worker as runtime
    from agent.loop import Outcome
    from contracts import FinalAnswer
    class Client:
        def __init__(self,*a,**kw):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*_):pass
    monkeypatch.setattr(runtime,'AsyncOpenAI',Client)
    monkeypatch.setattr(runtime,'MCPClient',Client)
    monkeypatch.setattr(runtime,'OPENAI_MODEL','scripted-client')
    monkeypatch.setattr(runtime,'MCP_BEARER_TOKEN','unused-by-scripted-client')
    monkeypatch.setenv('OPENAI_API_KEY','unused-by-scripted-client')
    monkeypatch.setenv('USE_MEMORY','true');monkeypatch.setenv('AGENT_MODE','single')
    async def context(*_):return ''
    async def prepare(remote,*_):return remote,''
    async def loop(*a,**kw):return Outcome(FinalAnswer(answer='fixture',claims=[]),'rate_limited',0,0)
    calls=[]
    async def extract(*a,**kw):calls.append(True);return []
    monkeypatch.setattr(runtime,'prepare_context',context);monkeypatch.setattr(runtime,'prepare',prepare)
    monkeypatch.setattr(runtime,'run_loop',loop);monkeypatch.setattr(runtime,'extract',extract)
    asyncio.run(runtime.execute({'question':'fixture','task_id':str(uuid4())}))
    assert calls==[]


@pytest.fixture
def rate_job(monkeypatch):
    monkeypatch.setenv('OPENAI_BASE_URL','http://rate-'+uuid4().hex+'/v1')
    monkeypatch.setenv('OPENAI_MODEL','rate-fixture')
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        owner=conn.execute('INSERT INTO users(username) VALUES(%s) RETURNING user_id',('rate-'+uuid4().hex,)).fetchone()[0]
    job=worker.claim(new(owner))
    yield job
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        limits.lock_task(conn,job['task_id']);limits.stop_task(conn,job['task_id'],'canceled')


def reserve(job,amount=100):
    call=uuid4()
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        limits.reserve(conn,job['task_id'],job['token'],{'call_id':str(call),'requested_model':'rate-fixture','reserved_tokens':amount})
    return call


@pytest.mark.integration
@integration
def test_atomic_shared_rpm_and_tpm_do_not_over_admit(rate_job,monkeypatch):
    from scripts.rate_limits import RateWait
    monkeypatch.setenv('PROVIDER_RPM','3');monkeypatch.setenv('PROVIDER_TPM','300')
    jobs=[rate_job]
    for _ in range(7):
        with psycopg.connect(**db_kwargs('agent','app')) as conn:
            owner=conn.execute('INSERT INTO users(username) VALUES(%s) RETURNING user_id',('rate-parallel-'+uuid4().hex,)).fetchone()[0]
        jobs.append(worker.claim(new(owner)))
    def attempt(job):
        try:return reserve(job)
        except RateWait:return None
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:admitted=list(pool.map(attempt,jobs))
        assert len([x for x in admitted if x])==3
    finally:
        for job in jobs[1:]:
            with psycopg.connect(**db_kwargs('agent','app')) as conn:
                limits.lock_task(conn,job['task_id']);limits.stop_task(conn,job['task_id'],'canceled')


@pytest.mark.integration
@integration
def test_inflight_limit_and_exactly_once_tpm_refund(rate_job,monkeypatch):
    from scripts.rate_limits import RateWait
    from scripts.provider_health import provider_key
    monkeypatch.setenv('PROVIDER_TPM','100');monkeypatch.setenv('PROVIDER_MAX_INFLIGHT','1')
    call=reserve(rate_job)
    with pytest.raises(RateWait):reserve(rate_job,1)
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        limits.lock_task(conn,rate_job['task_id'])
        payload={'control_call_id':str(call),'error_class':None,'usage':{'total_tokens':40}}
        limits.settle(conn,rate_job['task_id'],payload)
        limits.settle(conn,rate_job['task_id'],payload)
        tokens,inflight=conn.execute('SELECT tpm_tokens,inflight FROM rate_buckets WHERE provider=%s',(provider_key(),)).fetchone()
        assert 60<=tokens<61 and inflight==0
    assert reserve(rate_job,60)


@pytest.mark.integration
@integration
def test_database_clock_refills_and_expired_inflight_is_reclaimed(rate_job,monkeypatch):
    from scripts.provider_health import provider_key
    monkeypatch.setenv('PROVIDER_RPM','1');monkeypatch.setenv('PROVIDER_TPM','100');monkeypatch.setenv('PROVIDER_MAX_INFLIGHT','1')
    reserve(rate_job)
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        conn.execute("UPDATE rate_buckets SET updated_at=clock_timestamp()-interval '61 seconds' WHERE provider=%s",(provider_key(),))
        conn.execute("UPDATE rate_leases SET expires_at=clock_timestamp()-interval '1 second' WHERE provider=%s",(provider_key(),))
    assert reserve(rate_job)


@pytest.mark.integration
@integration
def test_disabled_limits_preserve_unrestricted_admission(rate_job,monkeypatch):
    for key in ['PROVIDER_RPM','PROVIDER_TPM','PROVIDER_MAX_INFLIGHT']:monkeypatch.delenv(key,raising=False)
    for _ in range(12):assert reserve(rate_job)


@pytest.mark.integration
@integration
def test_rate_wait_releases_transaction_locks_and_ends_rate_limited(rate_job,monkeypatch):
    import threading
    from contracts import FinalAnswer
    from scripts import rate_limits
    from scripts.provider_health import provider_key
    monkeypatch.setenv('PROVIDER_RPM','1');monkeypatch.setenv('RATE_WAIT_MAX_SECONDS','0.2')
    reserve(rate_job)
    waiting=threading.Event();original=rate_limits.acquire
    def acquire(*args):
        try:return original(*args)
        except rate_limits.RateWait:
            waiting.set();raise
    monkeypatch.setattr(rate_limits,'acquire',acquire)
    def runtime(question,task_id,emit,**kwargs):
        try:kwargs['control_check']({'call_id':str(uuid4()),'requested_model':'rate-fixture','reserved_tokens':100})
        except limits.TaskStopped as exc:
            assert str(exc)=='rate_limited'
            emit('termination',{'scope':'task','reason':str(exc)})
        else:raise AssertionError('Depleted bucket admitted a request')
        return FinalAnswer(answer='fixture',claims=[])
    monkeypatch.setattr(worker,'run_runtime',runtime)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(worker.process,rate_job)
        assert waiting.wait(2)
        with psycopg.connect(**db_kwargs('agent','app')) as conn:
            conn.execute("SET LOCAL lock_timeout='100ms'")
            limits.lock_task(conn,rate_job['task_id'])
            conn.execute('SELECT provider FROM rate_buckets WHERE provider=%s FOR UPDATE',(provider_key(),))
        future.result(timeout=2)
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        assert conn.execute('SELECT status,error FROM tasks WHERE task_id=%s',(rate_job['task_id'],)).fetchone()==('failed','rate_limited')
        assert conn.execute('SELECT count(*) FROM model_reservations WHERE task_id=%s',(rate_job['task_id'],)).fetchone()[0]==1


@pytest.mark.integration
@integration
def test_unknown_usage_frees_inflight_but_does_not_invent_token_refund(rate_job,monkeypatch):
    from scripts.provider_health import provider_key
    monkeypatch.setenv('PROVIDER_TPM','100');monkeypatch.setenv('PROVIDER_MAX_INFLIGHT','1')
    call=reserve(rate_job)
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        limits.lock_task(conn,rate_job['task_id'])
        limits.settle(conn,rate_job['task_id'],{'control_call_id':str(call),'error_class':'retryable','usage':None})
        tokens,inflight=conn.execute('SELECT tpm_tokens,inflight FROM rate_buckets WHERE provider=%s',(provider_key(),)).fetchone()
        assert tokens<1 and inflight==0
