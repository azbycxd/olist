import os
from uuid import uuid4
import pytest
import psycopg
from fastapi.testclient import TestClient
from api.tasks import app
from config import db_kwargs

integration=pytest.mark.skipif(os.getenv('RUN_DB_TESTS')!='1',reason='local database required')


def test_liveness_endpoint_does_not_require_database():
    assert TestClient(app).get('/healthz').status_code==200


def test_startup_rejects_missing_required_settings(monkeypatch):
    from db_pool import validate_settings
    monkeypatch.delenv('AGENT_DB_PASSWORD',raising=False)
    with pytest.raises(ValueError,match='AGENT_DB_PASSWORD'): validate_settings('api')


@pytest.mark.integration
@integration
def test_worker_release_is_atomic_and_does_not_consume_claim_budget():
    from scripts import task_worker as worker
    from test_task_controls import new
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        owner=conn.execute('INSERT INTO users(username) VALUES(%s) RETURNING user_id',('release-'+uuid4().hex,)).fetchone()[0]
    ident=new(owner)
    job=worker.claim(ident)
    try:
        for _ in range(4):
            worker.release(job)
            job=worker.claim(ident)
            assert job is not None
        with psycopg.connect(**db_kwargs('agent','app')) as conn:
            assert conn.execute('SELECT claim_count,released_count FROM tasks WHERE task_id=%s',(ident,)).fetchone()==(5,4)
    finally:
        with psycopg.connect(**db_kwargs('agent','app')) as conn:
            conn.execute("UPDATE tasks SET status='canceled',lease_token=NULL,lease_expires_at=NULL WHERE task_id=%s",(ident,))


@pytest.mark.integration
@integration
def test_pool_reuses_connection_and_local_timeout_resets():
    from db_pool import connection,close_all
    close_all()
    with connection('mcp','olist','reader') as conn:
        first=conn.info.backend_pid
        default=conn.execute('SHOW statement_timeout').fetchone()[0]
        conn.execute("SET LOCAL statement_timeout='123ms'")
    with connection('mcp','olist','reader') as conn:
        assert conn.info.backend_pid==first
        assert conn.execute('SHOW statement_timeout').fetchone()[0]==default
    close_all()


def test_query_paths_have_no_session_level_set():
    import ast,re
    from pathlib import Path
    paths=[*Path('mcp_olist').glob('*.py'),Path('scripts/findings.py')]
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node,ast.Constant) and isinstance(node.value,str):
                assert not re.match(r'\s*SET\s+(?!LOCAL\b|TRANSACTION\b)',node.value,re.I),path


@pytest.mark.integration
@integration
def test_worker_olist_pool_is_lazy_readonly_and_both_close():
    import db_pool
    from scripts.findings import current_version
    db_pool.close_all()
    assert db_pool.ready('worker')
    assert ('worker','olist','reader') not in db_pool._pools
    current_version()
    with db_pool.connection('worker','olist','reader') as conn:
        assert conn.execute('SELECT current_user').fetchone()[0]=='agent_ro'
        conn.execute('SET TRANSACTION READ ONLY')
        assert conn.execute('SHOW transaction_read_only').fetchone()[0]=='on'
    pools=list(db_pool._pools.values())
    db_pool.close_all('worker')
    assert all(p.closed for p in pools)
    assert not db_pool._pools


@pytest.mark.integration
@integration
def test_checked_pool_replaces_terminated_backend():
    from db_pool import connection,close_all
    close_all()
    with connection('api') as conn:old=conn.info.backend_pid
    with psycopg.connect(**db_kwargs('agent')) as admin:
        admin.execute('SELECT pg_terminate_backend(%s)',(old,))
    with connection('api') as conn:
        assert conn.info.backend_pid!=old
        assert conn.execute('SELECT 1').fetchone()==(1,)
    close_all()


@pytest.mark.integration
@integration
def test_api_pool_exhaustion_returns_503(monkeypatch):
    import config
    from db_pool import connection,close_all
    close_all()
    monkeypatch.setattr(config,'API_POOL_MAX',1)
    monkeypatch.setattr(config,'DB_POOL_TIMEOUT_SECONDS',.05)
    with connection('api'):
        assert TestClient(app).get('/readyz').status_code==503
        assert TestClient(app).post('/login',json={'username':'absent','password':'long-enough-password'}).status_code==503
    close_all()


@pytest.mark.integration
@integration
def test_mcp_liveness_readiness_and_tool_pool_exhaustion(monkeypatch):
    import config
    from db_pool import connection,close_all
    from mcp_olist.server import create_app
    close_all()
    monkeypatch.setattr(config,'MCP_AGENT_POOL_MAX',1)
    monkeypatch.setattr(config,'DB_POOL_TIMEOUT_SECONDS',.05)
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        owner=conn.execute('INSERT INTO users(username) VALUES(%s) RETURNING user_id',('mcp-pool-'+uuid4().hex,)).fetchone()[0]
        ident=conn.execute("INSERT INTO tasks(user_id,question,status) VALUES(%s,'pool fixture','completed') RETURNING task_id",(owner,)).fetchone()[0]
    with TestClient(create_app(),base_url='http://localhost:8001') as client:
        assert client.get('/healthz').status_code==200
        assert client.get('/readyz').status_code==200
        with connection('mcp'):
            assert client.get('/healthz').status_code==200
            assert client.get('/readyz').status_code==503
            response=client.post('/mcp',headers={
                'Authorization':'Bearer '+config.MCP_BEARER_TOKEN,
                'Accept':'application/json, text/event-stream','x-task-id':str(ident),
                'Idempotency-Key':str(ident)+':pool'},
                json={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'list_tables','arguments':{}}})
            assert response.status_code==503
    close_all()
