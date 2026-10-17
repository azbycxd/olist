import os
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import psycopg
import pytest
from fastapi.testclient import TestClient
from api.tasks import app,event,password_hash,verify_password
from config import db_kwargs
from scripts.task_worker import claim,heartbeat,check_lease
from mcp_olist.leases import validate


def test_password_hash_has_per_user_salt():
    a=password_hash('some long password');b=password_hash('some long password')
    assert a!=b and verify_password('some long password',a)
    assert not verify_password('wrong password',a) and not verify_password('x',None)


@pytest.mark.integration
@pytest.mark.skipif(os.getenv('RUN_DB_TESTS')!='1',reason='database integration opt-in')
def test_default_single_task_runs_directly_and_keeps_memory_extraction(monkeypatch):
    from scripts import task_worker
    from contracts import FinalAnswer
    monkeypatch.setenv('MEMORY_API_SECRET','test-only-'+uuid4().hex)
    client=TestClient(app)
    auth=client.post('/register',json={'username':'single-'+uuid4().hex,'password':'independent-test-password'}).json()
    headers={'Authorization':'Bearer '+auth['access_token']}
    assert client.post('/tasks',headers=headers,json={'question':'test','agent_mode':'invalid'}).status_code==422
    ident=client.post('/tasks',headers=headers,json={'question':'Test only: single route'}).json()['task_id']
    try:
        config=client.get('/tasks/'+ident,headers=headers).json()['run_config']
        assert config['AGENT_MODE']=='single' and config['NUMBER_GATE']==config['USE_MEMORY']=='true'
        assert config['RAG_MODE']=='inject' and config['CONTEXT_STRATEGY']=='none'
        job=claim(ident)
        assert job['phase']=='execute' and client.get('/tasks/'+ident,headers=headers).json()['status']=='running'
        def runtime(question,task_id,emit,**kwargs):
            assert kwargs['phase']=='execute' and os.environ['USE_MEMORY']=='true'
            emit('termination',{'scope':'task','reason':'final_answer'})
            return FinalAnswer(answer='test fixture',claims=[])
        monkeypatch.setattr(task_worker,'run_runtime',runtime)
        for k,v in job['settings'].items():monkeypatch.setenv(k,str(v))
        task_worker.process(job)
        result=client.get('/tasks/'+ident,headers=headers).json()
        assert result['status']=='completed' and result['plan'] is None
        assert result['result']['answer']=='test fixture'
    finally:
        with psycopg.connect(**db_kwargs('agent','app')) as conn:
            conn.execute("UPDATE tasks SET status='canceled',lease_token=NULL WHERE task_id=%s",(ident,))


@pytest.mark.integration
@pytest.mark.skipif(os.getenv('RUN_DB_TESTS')!='1',reason='database integration opt-in')
def test_enqueue_auth_confirmation_sse_and_lease_fencing(monkeypatch):
    monkeypatch.setenv('MEMORY_API_SECRET','test-only-'+uuid4().hex)
    client=TestClient(app)
    name='api-test-'+uuid4().hex
    body={'username':name,'password':'independent-test-password'}
    result=client.post('/register',json=body)
    assert result.status_code==201
    headers={'Authorization':'Bearer '+result.json()['access_token']}
    assert client.post('/register',json=body).status_code==409
    assert client.post('/login',json={**body,'password':'incorrect-password'}).status_code==401
    assert client.post('/login',json=body).status_code==200
    other=client.post('/register',json={'username':'other-'+uuid4().hex,'password':'independent-test-password'}).json()
    foreign={'Authorization':'Bearer '+other['access_token']}
    created=client.post('/tasks',headers=headers,json={'question':'Test only: do not execute','agent_mode':'multi'})
    assert created.status_code==202
    ident=created.json()['task_id']
    try:
        assert client.get('/tasks/'+ident).status_code==401
        assert client.get('/tasks/'+ident,headers=foreign).status_code==404
        assert client.get('/tasks/'+ident+'/events',headers=foreign).status_code==404
        assert client.get('/tasks/'+ident,headers=headers).json()['status']=='pending'
        plan={'subtasks':[{'id':'a','question':'first'},{'id':'b','question':'second','depends_on':['a']}]}
        assert client.post('/tasks/'+ident+'/confirm',headers=headers,json=plan).status_code==409
        # A pending row locked by another transaction is skipped rather than waited on.
        with psycopg.connect(**db_kwargs('agent','app')) as locked:
            locked.execute('SELECT task_id FROM tasks WHERE task_id=%s FOR UPDATE',(ident,))
            with ThreadPoolExecutor(max_workers=1) as pool:
                assert pool.submit(claim,ident).result(timeout=3) is None
        job=claim(ident);assert str(job['task_id'])==ident and job['phase']=='plan'
        assert claim(ident) is None and heartbeat(job['task_id'],job['token'])
        with psycopg.connect(**db_kwargs('agent','app'),autocommit=True) as conn:
            with pytest.raises(ValueError):validate(conn,ident,str(uuid4()),states=('planning',))
            validate(conn,ident,job['token'],states=('planning',))
            conn.execute("UPDATE tasks SET lease_expires_at=now()-interval '1 second' WHERE task_id=%s",(ident,))
        assert not heartbeat(job['task_id'],job['token'])
        recovered=claim(ident);assert recovered['token']!=job['token']
        with psycopg.connect(**db_kwargs('agent','app'),autocommit=True) as conn:
            with pytest.raises(RuntimeError):check_lease(conn,job['task_id'],job['token'])
        from mcp_olist.blackboard import write_state
        write_state(ident,'planner',plan,str(recovered['token']))
        with psycopg.connect(**db_kwargs('agent','app'),autocommit=True) as conn:
            conn.execute("UPDATE tasks SET status='awaiting_confirmation',lease_token=NULL WHERE task_id=%s",(ident,))
        assert client.post('/tasks/'+ident+'/confirm',headers=foreign,json=plan).status_code==404
        bad={'subtasks':[{'id':'a','question':'q','depends_on':['a']}]}
        assert client.post('/tasks/'+ident+'/confirm',headers=headers,json=bad).status_code==422
        assert client.post('/tasks/'+ident+'/confirm',headers=headers,json=plan).status_code==200
        assert client.post('/tasks/'+ident+'/confirm',headers=headers,json=plan).status_code==409
        execution=claim(ident);assert execution['phase']=='execute'
        def append(i):
            with psycopg.connect(**db_kwargs('agent','app')) as conn:return event(conn,ident,'test',{'i':i})
        with ThreadPoolExecutor(max_workers=4) as pool: seqs=list(pool.map(append,range(8)))
        assert len(set(seqs))==8
        with psycopg.connect(**db_kwargs('agent','app'),autocommit=True) as conn:
            conn.execute("UPDATE tasks SET status='completed' WHERE task_id=%s",(ident,))
        response=client.get('/tasks/'+ident+'/events',headers={**headers,'Last-Event-ID':str(min(seqs))})
        assert response.status_code==200 and f'id: {min(seqs)}\n' not in response.text
        assert f'id: {max(seqs)}\n' in response.text
        assert client.get('/tasks/'+ident+'/results/'+str(uuid4()),headers=foreign).status_code==404
        assert client.get('/tasks/'+ident,headers=headers).json()['usage']['total_tokens'] is None
    finally:
        with psycopg.connect(**db_kwargs('agent','app')) as conn:
            conn.execute("UPDATE tasks SET status='canceled',lease_token=NULL WHERE task_id=%s",(ident,))
