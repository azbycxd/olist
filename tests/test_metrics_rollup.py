"""Durable counters survive retention and concurrent event writers."""
import inspect
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest


def test_scrape_has_no_event_scan_or_usage_loop():
    from api import metrics
    source=inspect.getsource(metrics.DurableMetrics.collect)
    assert 'FROM events' not in source and 'JOIN events' not in source
    assert 'usage_summary(' not in source


def snapshot():
    from api.metrics import render
    from prometheus_client.parser import text_string_to_metric_families
    return {(s.name,tuple(sorted(s.labels.items()))):s.value for f in text_string_to_metric_families(render().decode())
            for s in f.samples if s.name.endswith(('_total','_count','_sum','_bucket'))}


@pytest.mark.integration
@pytest.mark.skipif(os.getenv('RUN_DB_TESTS')!='1',reason='local database required')
def test_retention_and_concurrent_event_writes_keep_counters():
    import psycopg
    from config import db_kwargs
    from api.tasks import event
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        owner=conn.execute("INSERT INTO users(username,data_scope) VALUES(%s,ARRAY['ALL']) RETURNING user_id",('rollup-'+uuid4().hex,)).fetchone()[0]
        ids=[conn.execute("INSERT INTO tasks(user_id,question,status) VALUES(%s,'rollup fixture','completed') RETURNING task_id",(owner,)).fetchone()[0] for _ in range(12)]
    before=snapshot()
    def write(ident):
        with psycopg.connect(**db_kwargs('agent','app')) as conn:
            event(conn,ident,'model_call',{'error_class':'retryable','usage':{'prompt_tokens':100,'completion_tokens':7,'prompt_cache_hit_tokens':20}},107,25)
            event(conn,ident,'sql_execution',{'sql_hash':'fixture'},latency_ms=5)
            event(conn,ident,'worker_claimed',{'recovered':True})
            event(conn,ident,'number_gate',{'replaced':['1','2']})
    with ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(write,ids))
    after=snapshot()
    def delta(name,labels=()):return after.get((name,labels),0)-before.get((name,labels),0)
    assert delta('olist_model_calls_total',(('error_class','retryable'),))==12
    assert delta('olist_tokens_total',(('kind','input'),))==1200
    assert delta('olist_model_duration_seconds_count')==12
    assert delta('olist_sql_duration_seconds_count')==12
    assert delta('olist_gate_replacements_total')==24
    # Admin-only test deletion emulates the future retention owner, without
    # relaxing the application's current append-only permission boundary.
    with psycopg.connect(**db_kwargs('agent')) as conn:
        conn.execute("SET LOCAL session_replication_role='replica'")
        conn.execute('DELETE FROM events WHERE task_id=ANY(%s::uuid[])',(ids,))
    assert snapshot()==after
    # Deletion must not make a later recovery look like the first queue claim.
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        event(conn,ids[0],'worker_claimed',{'recovered':True})
    final=snapshot()
    assert final[('olist_queue_wait_seconds_count',())]==after[('olist_queue_wait_seconds_count',())]
