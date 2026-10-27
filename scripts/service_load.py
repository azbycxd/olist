"""Local HTTP model double + real API, SSE, MCP, workers and PostgreSQL."""
import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

import httpx
import psycopg
from psycopg.types.json import Jsonb
from config import db_kwargs
from scripts.step12_experiments import receipt, source_identity


def scoped_worker(ids):
    from scripts import task_worker
    original=task_worker.claim
    task_worker.claim=lambda:next((job for ident in ids if (job:=original(ident))),None)
    task_worker.main()


def run(label,workers=4,count=20,rpm=0,tpm=0,sql=True):
    from eval.robustness import start_private_mcp,read_tasks
    from api.memories import issue
    calls=[];samples=[];stop=threading.Event();lock=threading.Lock()
    # Independent fake-provider token buckets, using ACTUAL usage, not reservation.
    balance=[float(rpm),float(tpm)];last=[time.monotonic()]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            actual=1000
            with lock:
                now=time.monotonic();elapsed=now-last[0];last[0]=now
                for i,cap in enumerate((rpm,tpm)):
                    if cap:balance[i]=min(cap,balance[i]+elapsed*cap/60)
                limited=(rpm and balance[0]<1) or (tpm and balance[1]<actual)
                status=429 if limited else 200
                if not limited:
                    if rpm:balance[0]-=1
                    if tpm:balance[1]-=actual
                calls.append({'at':now,'status':status,'actual_tokens':0 if limited else actual})
            if limited:payload={'error':{'message':'HTTP model double rate threshold'}}
            else:
                time.sleep(1)
                has_result=any(m.get('role')=='tool' for m in body['messages'])
                name='run_sql' if sql and not has_result else 'final_answer'
                args={'sql':'SELECT count(*) AS n FROM orders'} if name=='run_sql' else {'answer':'HTTP替身完成','claims':[]}
                message={'role':'assistant','content':None,'tool_calls':[{'id':uuid4().hex,'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}
                payload={'id':'fixture','object':'chat.completion','created':0,'model':'load-fixture','choices':[{'index':0,'message':message,'finish_reason':'tool_calls'}],'usage':{'prompt_tokens':900,'completion_tokens':100,'total_tokens':actual}}
            data=json.dumps(payload).encode()
            try:
                self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
    threading.Thread(target=server.serve_forever,daemon=True).start()
    mcp,url=start_private_mcp();children=[];streams=[];pool=None;api=None
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    env={**os.environ,'OLIST_LOAD_DOTENV':'0','OPENAI_BASE_URL':f'http://127.0.0.1:{server.server_port}/v1','OPENAI_MODEL':'load-'+uuid4().hex,'MCP_URL':url}
    for key in ('DEEPSEEK_MODEL','DEEPSEEK_BASE_URL','DEEPSEEK_API_KEY'):env.pop(key,None)
    started=time.monotonic();ids=[];sse_counts=[]
    try:
        api=subprocess.Popen([sys.executable,'-m','uvicorn','api.tasks:app','--host','127.0.0.1','--port',str(port),'--no-access-log'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        base=f'http://127.0.0.1:{port}'
        with httpx.Client(base_url=base,timeout=15) as client:
            for _ in range(100):
                try:
                    if client.get('/readyz').status_code==200:break
                except httpx.HTTPError:pass
                if api.poll() is not None:raise RuntimeError('Private API startup failed')
                time.sleep(.1)
            else:raise TimeoutError('Private API not ready')
            # Create isolated identities directly, then submit through the real API.
            with psycopg.connect(**db_kwargs('agent','app')) as conn:
                owners=[conn.execute("INSERT INTO users(username,data_scope) VALUES(%s,ARRAY['ALL']) RETURNING user_id",('load-'+uuid4().hex,)).fetchone()[0] for _ in range(count)]
            tokens=[issue(owner) for owner in owners]
            def submit(token):
                response=client.post('/tasks',headers={'Authorization':'Bearer '+token},json={'question':'工程服务 HTTP 替身任务'})
                response.raise_for_status();return response.json()['task_id']
            with ThreadPoolExecutor(max_workers=count) as submitters:ids=list(submitters.map(submit,tokens))
            with psycopg.connect(**db_kwargs('agent','app')) as conn:
                conn.execute('UPDATE tasks SET run_config=run_config||%s WHERE task_id=ANY(%s::uuid[])',(Jsonb({'RAG_MODE':'off','USE_MEMORY':'false'}),ids))
            def stream(pair):
                ident,token=pair;n=0
                with httpx.stream('GET',base+f'/tasks/{ident}/events',headers={'Authorization':'Bearer '+token},timeout=350) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if line.startswith('event:'):n+=1
                return n
            pool=ThreadPoolExecutor(max_workers=count)
            streams=[pool.submit(stream,pair) for pair in zip(ids,tokens)]
            def sample():
                with psycopg.connect(**db_kwargs('agent','admin'),autocommit=True) as conn:
                    while not stop.is_set():
                        counts=dict(conn.execute("SELECT application_name,count(*) FROM pg_stat_activity WHERE application_name LIKE 'olist:%%' GROUP BY application_name").fetchall())
                        samples.append({'elapsed_seconds':time.monotonic()-started,'counts':counts,'total':sum(counts.values())})
                        stop.wait(.02)
            sampler=threading.Thread(target=sample);sampler.start()
            for n in range(workers):
                children.append(subprocess.Popen([sys.executable,'-m','scripts.service_load','worker','--ids',','.join(ids)],env={**env,'WORKER_ID':'load-'+uuid4().hex},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True))
            deadline=time.monotonic()+330
            while time.monotonic()<deadline:
                tasks=read_tasks(ids)
                if all(t['status'] in {'completed','failed','canceled'} for t in tasks):break
                if any(p.poll() is not None for p in children):raise RuntimeError('Load worker exited unexpectedly')
                time.sleep(.2)
            else:raise TimeoutError('Load tasks did not terminate')
            sse_counts=[future.result(timeout=5) for future in streams]
            stop.set();sampler.join(timeout=5)
        import config
        cap=config.API_POOL_MAX+config.MCP_AGENT_POOL_MAX+config.MCP_OLIST_POOL_MAX+workers*(config.WORKER_AGENT_POOL_MAX+config.WORKER_OLIST_POOL_MAX)
        elapsed=time.monotonic()-started
        receipt('b1_pool_'+label if sql else 'b2_rate_'+label,{'model_kind':'HTTP model double; no real-model performance or quality claims','source_hashes':source_identity(),
            'workers':workers,'task_count':count,'completed':sum(t['status']=='completed' for t in tasks),
            'wall_ms':elapsed*1000,'request_count':len(calls),'http_429':sum(c['status']==429 for c in calls),
            'actual_tokens':sum(c['actual_tokens'] for c in calls),'actual_tpm_over_elapsed':sum(c['actual_tokens'] for c in calls)*60/elapsed,
            'peak_rolling_60s_tokens':max((sum(d['actual_tokens'] for d in calls if c['at']-60<d['at']<=c['at']) for c in calls),default=0),
            'provider_fixture_rpm':rpm,'provider_fixture_tpm':tpm,
            'connection_cap':cap,'connection_cap_formula':'API + MCP agent + MCP olist + workers * (worker agent + worker olist)',
            'connection_peak':max(s['total'] for s in samples),'connection_samples':samples,
            'sse_connections':len(streams),'sse_event_counts':sse_counts,'tasks':tasks,'calls':calls})
        assert max(s['total'] for s in samples)<=cap
        if sql:assert all(t['status']=='completed' for t in tasks)
    finally:
        stop.set()
        for process in children:
            process.terminate()
        for process in children:
            try:process.wait(timeout=30)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
        if api:api.terminate();api.wait(timeout=10)
        mcp.terminate();mcp.wait(timeout=10)
        server.shutdown();server.server_close()
        if pool:pool.shutdown(wait=False,cancel_futures=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['worker','pool','rate'])
    parser.add_argument('--ids');parser.add_argument('--label',default='after')
    parser.add_argument('--workers',type=int,default=4);parser.add_argument('--count',type=int,default=20)
    parser.add_argument('--rpm',type=int,default=0);parser.add_argument('--tpm',type=int,default=0)
    args=parser.parse_args()
    if args.mode=='worker':scoped_worker(args.ids.split(','))
    else:run(args.label,args.workers,args.count,args.rpm,args.tpm,sql=args.mode=='pool')
