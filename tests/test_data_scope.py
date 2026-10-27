"""Data-scope checks and real PostgreSQL default-deny RLS."""
import os
from uuid import uuid4
import pytest


def test_scope_precheck_rejects_foreign_state_and_national_aggregate():
    from mcp_olist.scopes import check_sql
    assert check_sql("SELECT count(*) FROM customers WHERE customer_state='RJ'",['SP'])['error']=='forbidden_dimension'
    assert check_sql('SELECT count(*) FROM orders',['SP'])['error']=='forbidden_dimension'
    assert check_sql("SELECT count(*) FROM customers WHERE customer_state='SP'",['SP']) is None
    assert check_sql('SELECT count(*) FROM orders',['ALL']) is None


@pytest.mark.parametrize('function',["set_config('app.allowed_states','ALL',true)","current_setting('app.allowed_states')"])
def test_model_cannot_change_or_inspect_scope(function):
    from mcp_olist.sql_guard import guard_sql,UnsafeSQL
    with pytest.raises(UnsafeSQL):guard_sql('SELECT '+function)


@pytest.mark.integration
@pytest.mark.skipif(os.getenv('RUN_DB_TESTS')!='1',reason='local databases required')
def test_reader_unset_scope_denies_and_scoped_queries_cannot_escape():
    import psycopg
    from config import db_kwargs
    with psycopg.connect(**db_kwargs('olist','reader')) as conn:
        conn.execute('SET TRANSACTION READ ONLY')
        assert conn.execute('SELECT count(*) FROM customers').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM orders').fetchone()[0]==0
        for table in ('order_items','order_payments','order_reviews'):
            assert conn.execute('SELECT count(*) FROM '+table).fetchone()[0]==0
        conn.execute("SET LOCAL app.allowed_states='SP'")
        assert conn.execute('SELECT DISTINCT customer_state FROM customers').fetchall()==[('SP',)]
        assert not conn.execute("SELECT 1 FROM pg_roles WHERE rolname=current_user AND (rolbypassrls OR rolsuper)").fetchone()
        assert not conn.execute("SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='customers' AND tableowner=current_user").fetchone()


@pytest.mark.integration
@pytest.mark.skipif(os.getenv('RUN_DB_TESTS')!='1',reason='local databases required')
def test_sp_task_rejects_rj_and_previous_broader_cached_result():
    import psycopg
    from config import db_kwargs
    from mcp_olist.service import run_query,get_saved_result
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        owner=conn.execute("INSERT INTO users(username,data_scope) VALUES(%s,ARRAY['ALL']) RETURNING user_id",('scope-'+uuid4().hex,)).fetchone()[0]
        task=conn.execute("INSERT INTO tasks(user_id,question,status) VALUES(%s,'scope fixture','running') RETURNING task_id",(owner,)).fetchone()[0]
    original=run_query('SELECT count(*) AS n FROM orders',str(task))
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        conn.execute("UPDATE users SET data_scope=ARRAY['SP'] WHERE user_id=%s",(owner,))
    assert run_query("SELECT count(*) FROM customers WHERE customer_state='RJ'",str(task))['error']=='forbidden_dimension'
    assert run_query('SELECT count(*) AS n FROM orders',str(task))['error']=='forbidden_dimension'
    assert get_saved_result(original['result_id'],str(task))['error']=='forbidden_dimension'
