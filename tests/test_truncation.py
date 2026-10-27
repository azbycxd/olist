import os
import psycopg
import pytest
from config import db_kwargs
from mcp_olist.service import run_query,get_saved_result
from test_idempotency import task

pytestmark=[pytest.mark.integration,pytest.mark.skipif(os.getenv('RUN_DB_TESTS')!='1',reason='local DB required')]


@pytest.mark.parametrize('statement,count,truncated',[
    ('SELECT order_id FROM (SELECT order_id FROM orders LIMIT 1000) AS exact_rows',1000,False),
    ('SELECT order_id FROM (SELECT order_id FROM orders LIMIT 1001) AS extra_row',1000,True),
    ('SELECT order_id FROM orders LIMIT 500',500,False),
])
def test_truncation_boundaries_are_explicit_and_persisted(task,statement,count,truncated):
    result=run_query(statement,task)
    assert result['row_count']==count and result['truncated'] is truncated
    assert get_saved_result(result['result_id'],task)['truncated'] is truncated
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        assert conn.execute('SELECT truncated FROM query_results WHERE result_id=%s',(result['result_id'],)).fetchone()[0] is truncated
    if truncated:
        assert '无序截断,不代表前 N 名,汇总请在 SQL 中完成' in result['notice']
    else:
        assert '无序截断' not in result['notice']


def test_ordered_truncation_has_flag_without_unordered_warning(task):
    result=run_query('SELECT order_id FROM orders ORDER BY order_id',task)
    assert result['truncated'] is True
    assert '无序截断' not in result['notice']


def test_explicit_limit_is_not_probed_or_reused_for_guard_cap(task,monkeypatch):
    executed=[];original=psycopg.Connection.execute
    def observe(conn,query,*args,**kwargs):
        if isinstance(query,str) and query.startswith('SELECT order_id FROM orders LIMIT '):
            executed.append(query)
        return original(conn,query,*args,**kwargs)
    monkeypatch.setattr(psycopg.Connection,'execute',observe)
    explicit=run_query('SELECT order_id FROM orders LIMIT 1000',task)
    capped=run_query('SELECT order_id FROM orders',task)
    assert explicit['row_count']==capped['row_count']==1000
    assert explicit['truncated'] is False
    assert capped['truncated'] is True
    assert explicit['result_id']!=capped['result_id']
    assert executed==['SELECT order_id FROM orders LIMIT 1000','SELECT order_id FROM orders LIMIT 1001']


def test_public_sql_matches_saved_rows_and_hash_but_execution_probes_one_more(task,monkeypatch):
    import hashlib
    from agent.sql_normalize import normalize_sql
    from api.tasks import result as api_result
    executed=[];original=psycopg.Connection.execute
    def observe(conn,query,*args,**kwargs):
        if isinstance(query,str) and query.startswith('SELECT order_id FROM orders ORDER BY order_id LIMIT '):executed.append(query)
        return original(conn,query,*args,**kwargs)
    monkeypatch.setattr(psycopg.Connection,'execute',observe)
    result=run_query('SELECT order_id FROM orders ORDER BY order_id',task)
    assert executed==['SELECT order_id FROM orders ORDER BY order_id LIMIT 1001']
    assert result['sql'].endswith('LIMIT 1000')
    assert get_saved_result(result['result_id'],task)['sql']==result['sql']
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        sql,digest=conn.execute('SELECT sql,sql_hash FROM query_results WHERE result_id=%s',(result['result_id'],)).fetchone()
        owner=conn.execute('SELECT user_id FROM tasks WHERE task_id=%s',(task,)).fetchone()[0]
    assert sql==result['sql']
    assert digest==hashlib.sha256(normalize_sql(sql).encode()).hexdigest()
    assert api_result(task,result['result_id'],owner)['sql']==sql
    with psycopg.connect(**db_kwargs(role='reader')) as conn:
        assert len(conn.execute(sql).fetchall())==result['row_count']==1000
