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
