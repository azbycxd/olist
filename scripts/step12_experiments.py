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


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('scenario', choices=['a1'])
    parser.add_argument('--label', required=True, choices=['before','after'])
    args = parser.parse_args()
    persistent_503(args.label)
