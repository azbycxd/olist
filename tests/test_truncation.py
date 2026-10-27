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
