import asyncio
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb
from fastapi.testclient import TestClient

from config import db_kwargs,FINAL_CONFIG
from scripts import task_limits as limits,task_worker as worker
from api.tasks import app,issue
from agent.task_control import CONTROL,reservation_size

integration=pytest.mark.skipif(os.getenv('RUN_DB_TESTS')!='1',reason='database integration opt-in')


def test_request_reservation_counts_utf8_tools_and_output():
    a=reservation_size([{'role':'user','content':'订单'}],None,100)
    assert a>100 and reservation_size([{'role':'user','content':'订单'}],[{'name':'sql'}],100)>a
    assert reservation_size([{'role':'user','content':'订单'}],None,200)-a==100


def test_cancel_admission_checked_before_retry_without_second_model_call():
    from agent.model import request
    admitted=[];sent=[]
    async def admit(payload):
        admitted.append(payload)
        if len(admitted)==2:raise RuntimeError('canceled')
    async def create(**kw):sent.append(kw);raise RuntimeError('429 fixture')
    async def sleep(_):pass
    async def run():
        token=CONTROL.set(admit)
        try:
            with pytest.raises(RuntimeError,match='canceled'):
                await request(SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),'fixture',[],lambda *a:None,sleep=sleep)
        finally:CONTROL.reset(token)
    asyncio.run(run())
    assert len(sent)==1 and len(admitted)==2 and admitted[0]['call_id']!=admitted[1]['call_id']


@pytest.fixture
def owner():
    with psycopg.connect(**db_kwargs('agent','app')) as db:
        uid=db.execute('INSERT INTO users(username) VALUES(%s) RETURNING user_id',('controls-'+uuid4().hex,)).fetchone()[0]
    yield uid
    with psycopg.connect(**db_kwargs('agent','app')) as db:
        limits.owner_lock(db,uid)
        for (tid,) in db.execute("SELECT task_id FROM tasks WHERE user_id=%s AND status NOT IN ('failed','completed','canceled')",(uid,)).fetchall():limits.stop_task(db,tid,'canceled')


def new(owner):
    with psycopg.connect(**db_kwargs('agent','app')) as db:
        return db.execute("INSERT INTO tasks(user_id,question,background,run_config,deadline_at) VALUES(%s,'control fixture',true,%s,now()+interval '5 minutes') RETURNING task_id",(owner,Jsonb(FINAL_CONFIG))).fetchone()[0]


def state(tid):
    with psycopg.connect(**db_kwargs('agent','app')) as db:return db.execute('SELECT status,error,lease_token FROM tasks WHERE task_id=%s',(tid,)).fetchone()


@pytest.mark.integration
@integration
def test_cancel_owner_isolation_idempotence_and_fencing(owner,monkeypatch):
    monkeypatch.setenv('MEMORY_API_SECRET','test-only-'+uuid4().hex)
    client=TestClient(app);tid=new(owner);job=worker.claim(tid)
    headers={'Authorization':'Bearer '+issue(owner)}
    assert client.post(f'/tasks/{tid}/cancel',headers={'Authorization':'Bearer '+issue(uuid4())}).status_code==404
    assert client.post(f'/tasks/{tid}/cancel',headers=headers).json()['status']=='canceled'
    assert client.post(f'/tasks/{tid}/cancel',headers=headers).status_code==200
    assert state(tid)==('canceled','canceled',None) and not worker.heartbeat(tid,job['token'])
    from mcp_olist.leases import validate
    with psycopg.connect(**db_kwargs('agent','app')) as db:
        with pytest.raises(ValueError):validate(db,tid,job['token'])


@pytest.mark.integration
@integration
def test_per_user_parallel_limit_and_released_slot(owner,monkeypatch):
    monkeypatch.setenv('USER_MAX_RUNNING_TASKS','2')
    ids=[new(owner) for _ in range(3)]
    with ThreadPoolExecutor(max_workers=3) as pool:jobs=list(pool.map(worker.claim,ids))
    # SKIP LOCKED permits transient misses; retry pending tasks after locks release.
    jobs=[j or worker.claim(tid) for j,tid in zip(jobs,ids)]
    assert sum(j is not None for j in jobs)==2
    with psycopg.connect(**db_kwargs('agent','app')) as db:
        other=db.execute('INSERT INTO users(username) VALUES(%s) RETURNING user_id',('other-'+uuid4().hex,)).fetchone()[0]
    other_tid=new(other)
    assert worker.claim(other_tid) is not None
    with psycopg.connect(**db_kwargs('agent','app')) as db:
        limits.lock_task(db,other_tid);limits.stop_task(db,other_tid,'canceled')
        completed=next(j for j in jobs if j)
        limits.lock_task(db,completed['task_id']);limits.stop_task(db,completed['task_id'],'canceled')
    assert worker.claim(ids[jobs.index(None)]) is not None


@pytest.mark.integration
@integration
@pytest.mark.parametrize('phase',['pending','awaiting_confirmation','running'])
def test_total_deadline_includes_queue_and_confirmation(owner,phase):
    tid=new(owner)
    with psycopg.connect(**db_kwargs('agent','app')) as db:
        db.execute("UPDATE tasks SET status=%s,deadline_at=now()-interval '1 second' WHERE task_id=%s",(phase,tid))
    assert worker.claim(tid) is None and state(tid)==('failed','task_timeout',None)


@pytest.mark.integration
@integration
@pytest.mark.parametrize('stop_reason',['canceled','task_timeout'])
def test_watchdog_terminates_blocked_child(owner,monkeypatch,stop_reason):
    tid=new(owner);job=worker.claim(tid);started=threading.Event();children=[]
    # A local sleeping process stands in for a model request that never responds.
    def blocked(*args,on_process=None,**kw):
        child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])
        children.append(child);on_process(child);started.set();child.wait()
        raise RuntimeError('child ended')
    monkeypatch.setattr(worker,'run_runtime',blocked)
    for k,v in job['settings'].items():monkeypatch.setenv(k,str(v))
    t=threading.Thread(target=worker.process,args=(job,));t.start()
    assert started.wait(5)
    with psycopg.connect(**db_kwargs('agent','app')) as db:
        if stop_reason=='canceled':db.execute('UPDATE tasks SET cancel_requested_at=now() WHERE task_id=%s',(tid,))
        else:db.execute("UPDATE tasks SET deadline_at=now()-interval '1 second' WHERE task_id=%s",(tid,))
    t.join(4)
    try:
        assert not t.is_alive() and children[0].poll() is not None
        assert state(tid)==('canceled' if stop_reason=='canceled' else 'failed',stop_reason,None)
    finally:
        if children[0].poll() is None:children[0].kill()


@pytest.mark.integration
@integration
def test_atomic_quota_settlement_unknown_hold_and_utc_days(owner,monkeypatch):
    monkeypatch.setenv('USER_DAILY_TOKEN_QUOTA','1000')
    ids=[new(owner),new(owner)];jobs=[worker.claim(tid) for tid in ids]
    requests=[{'call_id':str(uuid4()),'reserved_tokens':600} for _ in ids]
    def reserve(i):
        try:
            with psycopg.connect(**db_kwargs('agent','app')) as db:limits.reserve(db,ids[i],jobs[i]['token'],requests[i])
            return True
        except limits.TaskStopped:return False
    with ThreadPoolExecutor(max_workers=2) as pool:accepted=list(pool.map(reserve,range(2)))
    assert sum(accepted)==1
    i=accepted.index(True)
    with psycopg.connect(**db_kwargs('agent','app')) as db:
        limits.reserve(db,ids[i],jobs[i]['token'],requests[i]) # idempotent
        limits.settle(db,ids[i],{'control_call_id':requests[i]['call_id'],'usage':{'total_tokens':120}})
        limits.settle(db,ids[i],{'control_call_id':requests[i]['call_id'],'usage':{'total_tokens':120}})
        assert limits.quota(db,owner)['used_tokens']==120 and limits.quota(db,owner)['held_tokens']==0
        second={'call_id':str(uuid4()),'reserved_tokens':300}
        limits.reserve(db,ids[i],jobs[i]['token'],second)
        limits.settle(db,ids[i],{'control_call_id':second['call_id'],'usage':None})
        limits.stop_task(db,ids[i],'canceled')
        q=limits.quota(db,owner);assert q['held_tokens']==300 and q['available_tokens']==580
        db.execute("INSERT INTO user_token_days VALUES(%s,%s::date-1,999999,999999)",(owner,q['usage_day']))
        assert limits.quota(db,owner)['available_tokens']==580
        # Simulate UTC rollover: settlement still charges the recorded request day.
        db.execute('UPDATE model_reservations SET usage_day=usage_day-1 WHERE call_id=%s',(second['call_id'],))
        limits.settle(db,ids[i],{'control_call_id':second['call_id'],'usage':{'total_tokens':50}})
        assert db.execute('SELECT used_tokens FROM user_token_days WHERE user_id=%s AND usage_day=%s::date-1',(owner,q['usage_day'])).fetchone()[0]==1000049


@pytest.mark.integration
@integration
def test_quota_denial_precedes_model_and_is_committed(owner,monkeypatch):
    monkeypatch.setenv('USER_DAILY_TOKEN_QUOTA','50')
    tid=new(owner);job=worker.claim(tid);sent=[]
    def fake(*a,control_check=None,**kw):
        control_check({'call_id':str(uuid4()),'reserved_tokens':100})
        sent.append(True)
    monkeypatch.setattr(worker,'run_runtime',fake)
    for k,v in job['settings'].items():monkeypatch.setenv(k,str(v))
    worker.process(job)
    assert not sent and state(tid)==('failed','daily_token_quota',None)


@pytest.mark.integration
@integration
def test_deadline_uses_wall_clock_after_transaction_began(owner):
    tid=new(owner);job=worker.claim(tid)
    with psycopg.connect(**db_kwargs('agent','app')) as db:
        db.execute("UPDATE tasks SET deadline_at=clock_timestamp()+interval '100 milliseconds' WHERE task_id=%s",(tid,))
        time.sleep(.15)
        with pytest.raises(limits.TaskStopped,match='task_timeout'):worker.check_lease(db,tid,job['token'])


@pytest.mark.integration
@integration
@pytest.mark.skipif(os.getenv('RUN_MCP_TESTS')!='1',reason='requires live MCP')
def test_real_subprocess_admission_and_usage_settlement_with_http_fixture(owner,monkeypatch):
    from eval.robustness import ModelFixture
    fixture=ModelFixture('success')
    try:
        monkeypatch.setenv('OPENAI_BASE_URL',fixture.url)
        monkeypatch.setenv('OPENAI_MODEL','local-http-fixture')
        monkeypatch.setenv('OPENAI_API_KEY','fixture-only')
        tid=new(owner);job=worker.claim(tid)
        job['settings']={**job['settings'],'RAG_MODE':'off'}
        for k,v in job['settings'].items():monkeypatch.setenv(k,str(v))
        worker.process(job)
        assert state(tid)[0]=='completed' and len(fixture.calls)==2
        with psycopg.connect(**db_kwargs('agent','app')) as db:
            rows=db.execute('SELECT reserved_tokens,status,actual_tokens FROM model_reservations WHERE task_id=%s',(tid,)).fetchall()
            assert len(rows)==2 and all(amount>0 and status=='settled' and actual==0 for amount,status,actual in rows)
            assert limits.quota(db,owner)['held_tokens']==0
            payloads=db.execute("SELECT payload FROM events WHERE task_id=%s AND type='model_call'",(tid,)).fetchall()
            assert len(payloads)==2 and all(p[0]['control_call_id'] for p in payloads)
    finally:fixture.close()
