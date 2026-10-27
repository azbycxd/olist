"""PII redaction and destructive maintenance run only in a disposable agent DB."""
import os
from uuid import uuid4
import pytest


def test_event_redaction_preserves_business_numbers_and_identifiers():
    from privacy import redact
    value={'text':'邮箱 alice@example.com 手机 13800138000 身份证 11010519491231002X CPF 529.982.247-25',
           'order_id':'13800138000abcdef0123456789abcdef','amount':'12345.67',
           'nested':['CPF: 52998224725',42],'sql_hash':'5299822472513812345678999999999999999999999999999999999999999999999'}
    out=redact(value)
    assert all(x not in out['text'] for x in ('alice@example.com','13800138000','11010519491231002X','529.982.247-25'))
    assert '52998224725' not in out['nested'][0]
    assert out['order_id']==value['order_id'] and out['amount']=='12345.67' and out['sql_hash']==value['sql_hash']
    assert value['text'].startswith('邮箱 alice')  # no mutation of business objects


@pytest.fixture
def isolated_agent():
    import psycopg
    from psycopg import sql
    from config import db_kwargs,ROOT
    from scripts.migrate import discover,LEDGER,apply_one
    name='test_retention_'+uuid4().hex
    with psycopg.connect(**db_kwargs('postgres'),autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        try:
            with psycopg.connect(**db_kwargs(name)) as conn:
                conn.execute(LEDGER);conn.commit()
                for migration in discover(ROOT/'sql/migrations'):
                    if migration.database=='agent':apply_one(conn,migration)
            with psycopg.connect(**db_kwargs(name,'app')) as conn:yield conn
        finally:
            admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))


def seed(conn):
    from psycopg.types.json import Jsonb
    owner=conn.execute("INSERT INTO users(username) VALUES('retention-fixture') RETURNING user_id").fetchone()[0]
    task=conn.execute("INSERT INTO tasks(user_id,question,status,created_at,updated_at) VALUES(%s,'old private question','completed','2020-01-01','2020-01-01') RETURNING task_id",(owner,)).fetchone()[0]
    refs=[conn.execute("INSERT INTO query_results(task_id,sql,rows,row_count,data_version,created_at) VALUES(%s,'SELECT 42 AS n','[{\"n\":42}]',1,'fixture','2020-01-01') RETURNING result_id",(task,)).fetchone()[0] for _ in range(2)]
    answer={'answer':'final answer retained','claims':[{'text':'claim','value':42,'evidence':[str(refs[0])]}]}
    conn.execute('UPDATE tasks SET result=%s WHERE task_id=%s',(Jsonb(answer),task))
    conn.execute("INSERT INTO events(task_id,seq,type,payload,created_at) VALUES(%s,1,'model_call','{\"error_class\":\"success\",\"usage\":{\"prompt_tokens\":5,\"completion_tokens\":2}}','2020-01-01')",(task,))
    conn.execute("INSERT INTO memories(user_id,key,value,source_quote) VALUES(%s,'style','\"concise\"','fixture')",(owner,))
    conn.commit()
    return owner,task,refs,answer


@pytest.mark.integration
@pytest.mark.skipif(os.getenv('RUN_DB_TESTS')!='1',reason='local disposable database required')
def test_retention_keeps_answer_references_and_monotonic_counters(isolated_agent):
    from scripts.maintenance import retain
    conn=isolated_agent
    _,task,refs,answer=seed(conn)
    before=conn.execute('SELECT metric,label,value FROM metrics_rollup ORDER BY metric,label').fetchall()
    report=retain(conn,days=30)
    assert report['events_deleted']==1
    assert conn.execute('SELECT result,question FROM tasks WHERE task_id=%s',(task,)).fetchone()==(answer,'[retained final answer]')
    assert conn.execute('SELECT result_id FROM query_results').fetchall()==[(refs[0],)]
    assert conn.execute('SELECT metric,label,value FROM metrics_rollup ORDER BY metric,label').fetchall()==before
    assert conn.execute("SELECT count(*) FROM maintenance_audit WHERE action='retention'").fetchone()[0]==1


@pytest.mark.integration
@pytest.mark.skipif(os.getenv('RUN_DB_TESTS')!='1',reason='local disposable database required')
def test_delete_user_cascades_and_audits(isolated_agent):
    from scripts.maintenance import delete_user
    conn=isolated_agent
    owner,task,refs,_=seed(conn)
    delete_user(conn,owner)
    for table in ('users','tasks','events','query_results','memories'):
        assert conn.execute('SELECT count(*) FROM '+table).fetchone()[0]==0
    assert conn.execute("SELECT subject_id FROM maintenance_audit WHERE action='user_delete'").fetchone()[0]==owner
