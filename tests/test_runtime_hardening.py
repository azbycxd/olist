"""Step 12.1 regression contracts; HTTP/model clients here are test doubles."""
import asyncio
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from random import Random
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import psycopg
from openai import APIStatusError

from agent.loop import run_loop
from agent.model import request
from tests.test_agent import Remote, completion, FINAL

from config import db_kwargs
from scripts import task_limits as limits, task_worker as worker

integration = pytest.mark.skipif(os.getenv('RUN_DB_TESTS') != '1', reason='requires local database')


def status_error(status, message='controlled failure', headers=None):
    response = httpx.Response(status, headers=headers, request=httpx.Request('POST', 'http://fixture/v1'))
    return APIStatusError(message, response=response, body={'error': {'message': message}})


def client_for(items):
    sent = []
    iterator = iter(items)
    async def create(**kwargs):
        sent.append(kwargs)
        item = next(iterator)
        if isinstance(item, Exception):
            raise item
        return item
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), sent


@pytest.mark.parametrize('status', [400, 401, 403, 404, 422])
def test_fatal_http_error_is_not_retried(status):
    client, sent = client_for([status_error(status)] * 4)
    events, waits = [], []
    async def sleep(value): waits.append(value)
    result = asyncio.run(run_loop('fixture', Remote(), client, 'fixture', lambda *e: events.append(e), sleep=sleep))
    assert len(sent) == 1 and waits == []
    assert result.termination == 'model_fatal'
    assert [e[1]['error_class'] for e in events if e[0] == 'model_call'] == ['fatal']


def test_context_length_400_has_context_limit_reason():
    client, sent = client_for([status_error(400, 'maximum context length exceeded')] * 4)
    async def sleep(_): pass
    outcome = asyncio.run(run_loop('fixture', Remote(), client, 'fixture', lambda *e: None, sleep=sleep))
    assert len(sent) == 1 and outcome.termination == 'context_limit'


@pytest.mark.parametrize('header', ['2', 'http-date'])
def test_retry_after_precedes_backoff(header):
    if header == 'http-date': header = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=2))
    client, sent = client_for([status_error(429, headers={'Retry-After': header}), completion([FINAL])])
    waits, events = [], []
    async def sleep(value): waits.append(value)
    asyncio.run(request(client, 'fixture', [], lambda *e: events.append(e), sleep=sleep))
    assert len(sent) == 2 and len(waits) == 1
    assert 0 < waits[0] <= 2
    if header == '2': assert waits == [2]
    assert events[0][1]['error_class'] == 'retryable'
    assert next(e[1] for e in events if e[0]=='model_retry_wait')['retry_wait_ms'] >= 0


def test_retry_after_two_seconds_uses_real_clock_and_reports_actual_wait():
    client, _ = client_for([status_error(429, headers={'Retry-After':'2'}), completion([FINAL])])
    events = []
    before = time.perf_counter()
    asyncio.run(request(client,'fixture',[],lambda *e: events.append(e)))
    assert 1.9 <= time.perf_counter()-before < 4
    assert 1900 <= next(e[1] for e in events if e[0]=='model_retry_wait')['retry_wait_ms'] < 4000


def test_failed_call_is_emitted_before_sleep_then_wait_is_separate():
    client,_=client_for([status_error(503),completion([FINAL])])
    order=[]
    async def sleep(_):order.append('sleep')
    asyncio.run(request(client,'fixture',[],lambda *e:order.append(e[0]),sleep=sleep))
    assert order==['model_call','sleep','model_retry_wait','model_call']


@pytest.mark.parametrize('status',[408,429,500,502,503,504])
def test_retryable_statuses_retry_once_then_succeed(status):
    client, sent = client_for([status_error(status),completion([FINAL])])
    async def sleep(_): pass
    assert asyncio.run(request(client,'fixture',[],lambda *e: None,sleep=sleep)) is not None
    assert len(sent)==2


def test_retry_after_is_capped_and_invalid_value_uses_jitter(monkeypatch):
    from agent.model import retry_delay
    monkeypatch.setattr('agent.model.uniform', lambda a,b: b/2)
    assert retry_delay(status_error(429,headers={'Retry-After':'999999'}),0)==8
    assert retry_delay(status_error(429,headers={'Retry-After':'invalid'}),1)==1


def test_retry_jitter_is_seeded_and_bounded(monkeypatch):
    import agent.model as model_module
    rng = Random(1201)
    monkeypatch.setattr(model_module, 'uniform', rng.uniform, raising=False)
    client, sent = client_for([status_error(503)] * 4)
    waits = []
    async def sleep(value): waits.append(value)
    assert asyncio.run(request(client, 'fixture', [], lambda *e: None, sleep=sleep)) is None
    expected = Random(1201)
    assert waits == [expected.uniform(0, cap) for cap in (1, 2, 4)]
    assert len(sent) == 4


def test_retry_wait_respects_remaining_task_time():
    from agent.task_control import CONTROL
    client, sent = client_for([status_error(503)] * 4)
    waits = []
    async def admit(_): return {'remaining_seconds': 0.01}
    async def sleep(value): waits.append(value)
    async def run():
        token = CONTROL.set(admit)
        try: return await request(client, 'fixture', [], lambda *e: None, sleep=sleep)
        finally: CONTROL.reset(token)
    asyncio.run(run())
    assert sum(waits) <= 0.01


@pytest.fixture
def circuit_job(monkeypatch):
    from test_task_controls import new
    model = 'circuit-test-' + uuid4().hex
    monkeypatch.setenv('OPENAI_MODEL', model)
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        owner = conn.execute('INSERT INTO users(username) VALUES(%s) RETURNING user_id', (model,)).fetchone()[0]
    job = worker.claim(new(owner))
    yield job, model
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        limits.lock_task(conn, job['task_id'])
        limits.stop_task(conn, job['task_id'], 'canceled')


def admit(job, model):
    call_id = str(uuid4())
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        limits.reserve(conn, job['task_id'], job['token'], {'call_id':call_id, 'reserved_tokens':100, 'requested_model':model})
    return call_id


def result(job, call_id, error='retryable'):
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        limits.lock_task(conn, job['task_id'])
        limits.settle(conn, job['task_id'], {'control_call_id':call_id, 'error_class':error, 'usage':None if error else {'total_tokens':1}})


def open_circuit(job, model):
    for _ in range(5): result(job, admit(job, model))


@pytest.mark.integration
@integration
def test_five_errors_open_circuit_and_deny_within_100ms(circuit_job):
    job, model = circuit_job
    open_circuit(job, model)
    started = time.perf_counter()
    with pytest.raises(limits.TaskStopped, match='provider_unavailable'): admit(job, model)
    assert time.perf_counter() - started < .1


@pytest.mark.integration
@integration
@pytest.mark.parametrize('probe_error', [None, 'retryable', 'fatal'])
def test_half_open_allows_one_probe_then_closes_or_reopens(circuit_job, probe_error):
    job, model = circuit_job
    open_circuit(job, model)
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        conn.execute("UPDATE provider_health SET open_until=clock_timestamp()-interval '1 second' WHERE model=%s", (model,))
    def attempt(_):
        try: return admit(job, model)
        except limits.TaskStopped: return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        admitted = [x for x in pool.map(attempt, range(4)) if x]
    assert len(admitted) == 1
    result(job, admitted[0], probe_error)
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        assert conn.execute('SELECT state FROM provider_health WHERE model=%s',(model,)).fetchone()[0] == ('closed' if probe_error is None else 'open')


@pytest.mark.integration
@integration
def test_concurrent_errors_and_duplicate_events_do_not_lose_or_double_counts(circuit_job):
    job, model = circuit_job
    calls = [admit(job, model) for _ in range(4)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda call: result(job,call), calls))
    result(job, calls[-1])
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        assert conn.execute('SELECT failure_count FROM provider_health WHERE model=%s',(model,)).fetchone()[0] == 4
    result(job, admit(job, model))
    with pytest.raises(limits.TaskStopped, match='provider_unavailable'): admit(job, model)


@pytest.mark.integration
@integration
def test_five_concurrent_tasks_open_before_any_backoff_finishes(circuit_job,monkeypatch):
    from test_task_controls import new
    from agent.task_control import CONTROL
    _,model=circuit_job
    jobs=[]
    for _ in range(5):
        with psycopg.connect(**db_kwargs('agent','app')) as conn:
            owner=conn.execute('INSERT INTO users(username) VALUES(%s) RETURNING user_id',('parallel-'+uuid4().hex,)).fetchone()[0]
        jobs.append(worker.claim(new(owner)))
    observed=[]
    async def run():
        admitted=0;sleeping=0;all_admitted=asyncio.Event();all_sleeping=asyncio.Event()
        async def one(job):
            async def control(req):
                nonlocal admitted
                with psycopg.connect(**db_kwargs('agent','app')) as conn:
                    response=limits.reserve(conn,job['task_id'],job['token'],req)
                admitted+=1
                if admitted==5:all_admitted.set()
                await all_admitted.wait()
                return response
            def emit(kind,payload,*_):
                if kind=='model_call':
                    with psycopg.connect(**db_kwargs('agent','app')) as conn:
                        limits.lock_task(conn,job['task_id']);limits.settle(conn,job['task_id'],payload)
            async def sleep(_):
                nonlocal sleeping
                sleeping+=1
                if sleeping==5:
                    with psycopg.connect(**db_kwargs('agent','app')) as conn:
                        observed.append(conn.execute('SELECT state,failure_count FROM provider_health WHERE model=%s',(model,)).fetchone())
                    all_sleeping.set()
                await all_sleeping.wait()
                raise asyncio.CancelledError  # No backoff is allowed to finish.
            client,_=client_for([status_error(503,headers={'Retry-After':'8'})])
            token=CONTROL.set(control)
            try:await request(client,model,[],emit,sleep=sleep)
            finally:CONTROL.reset(token)
        await asyncio.gather(*(one(job) for job in jobs),return_exceptions=True)
    try:
        asyncio.run(run())
        assert observed==[('open',5)]
    finally:
        for job in jobs:
            with psycopg.connect(**db_kwargs('agent','app')) as conn:
                limits.lock_task(conn,job['task_id']);limits.stop_task(conn,job['task_id'],'canceled')


@pytest.mark.integration
@integration
def test_fatal_and_unknown_do_not_reset_failures(circuit_job):
    job,model=circuit_job
    for _ in range(3):result(job,admit(job,model))
    for error in ['fatal','unknown']:
        result(job,admit(job,model),error)
        with psycopg.connect(**db_kwargs('agent','app')) as conn:
            assert conn.execute('SELECT failure_count FROM provider_health WHERE model=%s',(model,)).fetchone()[0]==3
    result(job,admit(job,model),None)
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        assert conn.execute('SELECT failure_count FROM provider_health WHERE model=%s',(model,)).fetchone()[0]==0
