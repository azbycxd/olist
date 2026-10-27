"""Version mutation tests are isolated from the real business database."""
import os
from uuid import uuid4
import pytest


def test_unknown_blackboard_version_is_not_resumed():
    from agent.state import resumable
    assert resumable({'schema_version':1})
    assert not resumable({'schema_version':999})
    assert not resumable({'plan':{}})


@pytest.mark.integration
@pytest.mark.skipif(os.getenv('RUN_DB_TESTS')!='1',reason='isolated database required')
def test_statement_write_changes_version_and_stale_finding_is_not_injected(monkeypatch):
    import psycopg
    from psycopg import sql
    from config import db_kwargs,ROOT
    from scripts.migrate import discover,LEDGER,apply_one
    names={name:'test_versions_'+name+'_'+uuid4().hex for name in ('agent','olist')}
    with psycopg.connect(**db_kwargs('postgres'),autocommit=True) as admin:
        created=[]
        try:
            for name in names.values():
                admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)));created.append(name)
            for kind,name in names.items():
                with psycopg.connect(**db_kwargs(name)) as conn:
                    conn.execute(LEDGER);conn.commit()
                    for m in discover(ROOT/'sql/migrations'):
                        if m.database==kind:apply_one(conn,m)
            with psycopg.connect(**db_kwargs(names['olist'])) as conn:
                conn.execute("INSERT INTO data_imports(data_version,manifest) VALUES('source-hash','{}')")
                conn.execute("INSERT INTO customers VALUES('customer','unique',10000,'city','SP')")
            from contextlib import contextmanager
            from scripts import findings
            @contextmanager
            def isolated_connection(component,database='agent',role='app'):
                with psycopg.connect(**db_kwargs(names[database],role)) as conn:yield conn
            monkeypatch.setattr(findings,'connection',isolated_connection)
            import mcp_olist.scopes
            monkeypatch.setattr(mcp_olist.scopes,'connection',isolated_connection)
            monkeypatch.setattr(findings,'embed',lambda *a,**kw:[[1.,0.,0.]])
            old=findings.current_version()
            with psycopg.connect(**db_kwargs(names['agent'])) as conn:
                owner=conn.execute("INSERT INTO users(username,data_scope) VALUES('version-fixture',ARRAY['ALL']) RETURNING user_id").fetchone()[0]
                task=conn.execute("INSERT INTO tasks(user_id,question,status) VALUES(%s,'q','running') RETURNING task_id",(owner,)).fetchone()[0]
                ref=uuid4()
                from psycopg.types.json import Jsonb
                conn.execute("INSERT INTO memories(user_id,type,key,value,source_quote,evidence,data_version,embedding,embedding_model,embedding_revision,source_task_id) VALUES(%s,'finding','old',%s,'old',%s,%s,'[1,0,0]',%s,%s,%s)",(owner,Jsonb({'text':'old conclusion','value':42,'question':'old direction'}),Jsonb([str(ref)]),old,findings.MODEL,findings.REVISION,task))
            with psycopg.connect(**db_kwargs(names['olist'])) as conn:
                conn.execute("UPDATE customers SET customer_city='changed' WHERE customer_id='customer'")
            new=findings.current_version()
            assert new!=old and new.startswith('source-hash:')
            result=findings.retrieve(task,'q')
            assert result[0]['status']=='stale_clue' and 'claim' not in result[0] and '需复核' in result[0]['notice']
        finally:
            for name in created:admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))


@pytest.mark.integration
@pytest.mark.skipif(os.getenv('RUN_DB_TESTS')!='1',reason='local agent database required')
def test_worker_discards_old_board_and_replans():
    import psycopg
    from config import db_kwargs
    from api.tasks import create_task,NewTask
    from scripts.task_worker import claim,release
    from psycopg.types.json import Jsonb
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        owner=conn.execute("INSERT INTO users(username,data_scope) VALUES(%s,ARRAY['ALL']) RETURNING user_id",('old-board-'+uuid4().hex,)).fetchone()[0]
    task=create_task(NewTask(question='version fixture',agent_mode='multi'),owner)['task_id']
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        conn.execute("INSERT INTO task_state(task_id,plan,subtasks,report,schema_version) VALUES(%s,'{}','{}',%s,999)",(task,Jsonb({'answer':'must not resume','claims':[]})))
        conn.execute('UPDATE tasks SET confirmed_at=now() WHERE task_id=%s',(task,))
    job=claim(task)
    assert job['phase']=='plan' and job['board'] is None
    release(job)
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        conn.execute("UPDATE tasks SET status='canceled' WHERE task_id=%s",(task,))
