"""Real local service experiments with an explicit HTTP model double; no model evaluation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

import psycopg
from config import ROOT, db_kwargs
from scripts.evidence import write_evidence


def receipt(name, payload):
    from datetime import datetime, timezone
    stem = 'step12_' + name + '_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid4().hex[:8]
    path = ROOT / 'evidence' / (stem + '.jsonl')
    path.write_text(json.dumps(payload, ensure_ascii=False, default=str) + '\n', encoding='utf-8')
    summary = {**payload, 'source_log': path.name, 'source_log_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    summary.pop('tasks', None)
    summary.pop('calls', None)
    output = write_evidence(stem + '.summary.json', summary)
    print(json.dumps({'receipt': output.name, **{k: payload[k] for k in ('wall_ms', 'request_count') if k in payload}}))
    return output


def source_identity():
    files = ['agent/model.py', 'scripts/runtime.py', 'scripts/task_worker.py', 'scripts/task_limits.py']
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files}


def persistent_503(label):
    from api.tasks import NewTask, create_task
    from eval.robustness import read_tasks
    from scripts.task_worker import claim, process
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            calls.append({'at_monotonic': time.monotonic(), 'status': 503})
            body = b'{"error":{"message":"Step12 HTTP model double: persistent 503","type":"server_error"}}'
            self.send_response(503)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    previous = dict(os.environ)
    try:
        # Credentials remain loaded from .env/Compose. Never emit request headers.
        os.environ['OPENAI_BASE_URL'] = f'http://127.0.0.1:{server.server_port}/v1'
        os.environ['OPENAI_MODEL'] = 'step12-http-503-' + uuid4().hex
        with psycopg.connect(**db_kwargs('agent', 'app')) as conn:
            owner = conn.execute('INSERT INTO users(username) VALUES(%s) RETURNING user_id', ('step12-'+uuid4().hex,)).fetchone()[0]
        ids = [create_task(NewTask(question='Step12 HTTP 替身故障实验'), owner)['task_id'] for _ in range(10)]
        durations = []
        started = time.perf_counter()
        for ident in ids:
            job = claim(ident)
            if job is None: raise AssertionError('Experiment task was not claimable')
            # Isolate request retry/circuit behavior from retrieval and preference extraction.
            job['settings'].update(RAG_MODE='off', USE_MEMORY='false')
            before = time.perf_counter()
            process(job)
            durations.append((time.perf_counter()-before)*1000)
        elapsed = (time.perf_counter()-started)*1000
        tasks = read_tasks(ids)
        if not all(t['status']=='failed' for t in tasks): raise AssertionError('Unexpected non-failed fixture task')
        receipt('a1_'+label, {'model_kind':'HTTP model double, persistent 503; NOT real-model performance/quality',
            'source_hashes':source_identity(), 'task_count':10, 'workers':1, 'dispatch':'background API enqueue; production worker claim/process',
            'overrides':{'RAG_MODE':'off','USE_MEMORY':'false'}, 'wall_ms':elapsed,
            'request_count':len(calls), 'task_durations_ms':durations, 'calls':calls, 'tasks':tasks})
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)
        os.environ.clear(); os.environ.update(previous)


def duplicate_sql(label):
    from mcp_olist import service
    from mcp_olist.sql_guard import guard_sql
    from scripts.task_worker import claim
    from api.tasks import create_task,NewTask
    from eval.robustness import read_tasks
    statement='SELECT count(*) AS n FROM orders'
    executable=guard_sql(statement)
    original_connect=psycopg.connect
    executed=[]
    class CountedConnection:
        def __init__(self,conn): self.conn=conn
        def __enter__(self): self.conn.__enter__(); return self
        def __exit__(self,*a): return self.conn.__exit__(*a)
        def __getattr__(self,name): return getattr(self.conn,name)
        def execute(self,query,*a,**kw):
            if query==executable: executed.append({'at_monotonic':time.monotonic(),'sql':query})
            return self.conn.execute(query,*a,**kw)
    def counted(*a,**kw):
        conn=original_connect(*a,**kw)
        return CountedConnection(conn) if kw.get('user')=='agent_ro' else conn
    with original_connect(**db_kwargs('agent','app')) as conn:
        owner=conn.execute('INSERT INTO users(username) VALUES(%s) RETURNING user_id',('sql-recovery-'+uuid4().hex,)).fetchone()[0]
    ident=create_task(NewTask(question='SQL 结果落库后响应丢失恢复替身'),owner)['task_id']
    first_job=claim(ident)
    psycopg.connect=counted
    started=time.perf_counter()
    try:
        first=service.run_query(statement,ident,str(first_job['token']))
        # Simulate the old worker disappearing after SQL commit but before the
        # caller receives its result. The production claim path issues a new fence.
        with original_connect(**db_kwargs('agent','app')) as conn:
            conn.execute("UPDATE tasks SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE task_id=%s",(ident,))
        next_job=claim(ident)
        second=service.run_query(statement,ident,str(next_job['token']))
        with original_connect(**db_kwargs('agent','app')) as conn:
            count=conn.execute('SELECT count(*) FROM query_results WHERE task_id=%s',(ident,)).fetchone()[0]
            conn.execute("UPDATE tasks SET status='completed',lease_token=NULL,lease_expires_at=NULL WHERE task_id=%s",(ident,))
        receipt('a3_'+label,{'model_kind':'Recovery control-flow double; no real model call; real PostgreSQL SQL and worker lease recovery',
            'scenario':'committed SQL response lost; expire old lease; production claim reissues lease; rerun identical SQL',
            'source_hashes':{'mcp_olist/service.py':hashlib.sha256((ROOT/'mcp_olist/service.py').read_bytes()).hexdigest()},
            'sql_execution_count':len(executed),'saved_result_count':count,'same_result_id':first['result_id']==second['result_id'],
            'wall_ms':(time.perf_counter()-started)*1000,'calls':executed,'tasks':read_tasks([ident])})
    finally: psycopg.connect=original_connect


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('scenario', choices=['a1','a3'])
    parser.add_argument('--label', required=True, choices=['before','after'])
    args = parser.parse_args()
    {'a1':persistent_503,'a3':duplicate_sql}[args.scenario](args.label)
