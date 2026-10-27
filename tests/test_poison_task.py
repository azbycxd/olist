import os
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest
from psycopg.types.json import Jsonb

from config import db_kwargs, FINAL_CONFIG
from scripts.task_worker import claim, heartbeat, MAX_CLAIMS

pytestmark = pytest.mark.skipif(os.getenv('RUN_DB_TESTS') != '1', reason='database integration opt-in')


@pytest.mark.parametrize('mode', ['single', 'multi'])
def test_three_leases_then_concurrent_fourth_pickup_fails(mode):
    with psycopg.connect(**db_kwargs('agent', 'app')) as db:
        owner = db.execute("INSERT INTO users(username,data_scope) VALUES(%s,ARRAY['ALL']) RETURNING user_id", ('poison-'+uuid4().hex,)).fetchone()[0]
        ident = db.execute("INSERT INTO tasks(user_id,question,background,run_config) VALUES(%s,'poison fixture',true,%s) RETURNING task_id",
                           (owner, Jsonb({**FINAL_CONFIG, 'AGENT_MODE':mode}))).fetchone()[0]
    try:
        for number in range(1, MAX_CLAIMS+1):
            job = claim(ident)
            assert job is not None
            with psycopg.connect(**db_kwargs('agent','app')) as db:
                assert db.execute('SELECT claim_count FROM tasks WHERE task_id=%s',(ident,)).fetchone()[0] == number
                db.execute("UPDATE tasks SET lease_expires_at=now()-interval '1 second' WHERE task_id=%s",(ident,))
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert list(pool.map(claim, [ident,ident])) == [None,None]
        assert not heartbeat(ident,job['token'])
        assert claim(ident) is None
        with psycopg.connect(**db_kwargs('agent','app')) as db:
            state = db.execute('SELECT status,error,claim_count,lease_token,lease_expires_at FROM tasks WHERE task_id=%s',(ident,)).fetchone()
            assert state[0]=='failed' and 'claim_limit_exceeded' in state[1]
            assert state[2:] == (3,None,None)
            assert db.execute("SELECT count(*) FROM events WHERE task_id=%s AND type='worker_claimed'",(ident,)).fetchone()[0] == 3
            events = db.execute("SELECT payload FROM events WHERE task_id=%s AND type='task_status'",(ident,)).fetchall()
            assert len(events)==1 and events[0][0]['attempted_claim']==4
    finally:
        with psycopg.connect(**db_kwargs('agent','app')) as db:
            db.execute("UPDATE tasks SET status='canceled',lease_token=NULL,lease_expires_at=NULL WHERE task_id=%s AND status!='failed'",(ident,))


def test_exhausted_pending_task_is_failed_without_execution():
    # Scoped calls make this safe beside unrelated queued tasks.
    with psycopg.connect(**db_kwargs('agent','app')) as db:
        owner=db.execute("INSERT INTO users(username,data_scope) VALUES(%s,ARRAY['ALL']) RETURNING user_id",('poison-pending-'+uuid4().hex,)).fetchone()[0]
        ident=db.execute("INSERT INTO tasks(user_id,question,background,claim_count) VALUES(%s,'pending poison fixture',true,3) RETURNING task_id",(owner,)).fetchone()[0]
    assert claim(ident) is None
    with psycopg.connect(**db_kwargs('agent','app')) as db:
        assert db.execute('SELECT status,claim_count FROM tasks WHERE task_id=%s',(ident,)).fetchone()==('failed',3)

# Explicitly excluded by the service-free CI job.
pytestmark = [pytestmark, pytest.mark.integration]
