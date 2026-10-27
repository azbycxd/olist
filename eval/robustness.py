"""Real queue/DB/MCP transport experiments; HTTP model fault fixtures are explicit."""
import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

from config import ROOT, FINAL_CONFIG, db_kwargs
from scripts.common import start_log, record
from scripts.evidence import write_evidence
from scripts.task_worker import claim, process


def create_tasks(questions, settings):
    with psycopg.connect(**db_kwargs('agent','app')) as db:
        owner=db.execute("INSERT INTO users(username,data_scope) VALUES(%s,ARRAY['ALL']) RETURNING user_id",('robustness-'+uuid4().hex,)).fetchone()[0]
        return [str(db.execute('INSERT INTO tasks(user_id,question,background,run_config) VALUES(%s,%s,true,%s) RETURNING task_id',
                              (owner,q,Jsonb(settings))).fetchone()[0]) for q in questions]


def read_tasks(ids):
    with psycopg.connect(**db_kwargs('agent','app')) as db:
        rows=db.execute('SELECT task_id,status,claim_count,error,lease_token,lease_expires_at,result FROM tasks WHERE task_id=ANY(%s::uuid[]) ORDER BY created_at,task_id',(ids,)).fetchall()
        result=[]
        for r in rows:
            events=[{'seq':e[0],'type':e[1],'payload':e[2],'latency_ms':float(e[3]),'at':str(e[4])} for e in db.execute('SELECT seq,type,payload,latency_ms,created_at FROM events WHERE task_id=%s ORDER BY seq',(r[0],)).fetchall()]
            result.append(dict(zip(('task_id','status','claim_count','error','lease_token','lease_expires_at','result'),(str(r[0]),*r[1:])),events=events))
        return result


def worker(ids, worker_id):
    os.environ['WORKER_ID']=worker_id
    # Same production claim SQL, scoped to this experiment's IDs so unrelated
    # user tasks cannot be consumed. Both processes compete for the same rows.
    while True:
        job=next((j for ident in ids if (j:=claim(ident)) is not None),None)
        if job:process(job)
        else:
            states=read_tasks(ids)
            if all(t['status'] in {'completed','failed','canceled'} for t in states):return
            time.sleep(.05)


def publish(name,summary):
    logger,path=start_log('step10_'+name)
    record(logger,'experiment',**summary)
    summary.update(source_log=path.name,source_log_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    receipt=write_evidence(path.stem+'.summary.json',summary)
    print('Evidence:',receipt.name)
    return summary


def concurrency():
    from mcp_olist.embedding_config import provenance
    identity=provenance(used=True)
    questions=[f'{state} 州 2017 年有多少客户？' for state in ('SP','RJ','MG','PR','RS','BA')]
    ids=create_tasks(questions,FINAL_CONFIG)
    stop=threading.Event();samples=[]
    def sample():
        with psycopg.connect(**db_kwargs('agent','admin'),autocommit=True) as db:
            while not stop.is_set():
                counts=dict(db.execute("SELECT COALESCE(usename,'background'),count(*) FROM pg_stat_activity WHERE backend_type='client backend' GROUP BY usename").fetchall())
                samples.append({'elapsed_s':time.perf_counter()-started,'counts':counts,'total_including_sampler':sum(counts.values())})
                stop.wait(.05)
    with psycopg.connect(**db_kwargs('agent','admin')) as db:
        limit=int(db.execute('SHOW max_connections').fetchone()[0])
        reserved=int(db.execute('SHOW superuser_reserved_connections').fetchone()[0])
    started=time.perf_counter();sampler=threading.Thread(target=sample);sampler.start()
    children=[]
    try:
        time.sleep(.1)
        for i in range(2):
            children.append(subprocess.Popen([sys.executable,'-m','eval.robustness','--worker',f'concurrent-{i+1}','--ids',','.join(ids)],stdout=subprocess.DEVNULL))
        deadline=started+300
        while any(p.poll() is None for p in children) and time.perf_counter()<deadline:time.sleep(.1)
        if any(p.poll() is None for p in children):raise TimeoutError('Concurrent workers did not finish')
    finally:
        for p in children:
            if p.poll() is None:p.kill()
            p.wait()
        stop.set();sampler.join(timeout=5)
    elapsed=(time.perf_counter()-started)*1000;tasks=read_tasks(ids)
    claims=[(t['task_id'],e) for t in tasks for e in t['events'] if e['type']=='worker_claimed']
    intervals=[]
    for t in tasks:
        start=next(e['at'] for e in t['events'] if e['type']=='worker_claimed')
        end=next(e['at'] for e in reversed(t['events']) if e['type']=='task_status')
        intervals.append((start,end))
    overlap=any(max(a[0],b[0])<min(a[1],b[1]) for i,a in enumerate(intervals) for b in intervals[i+1:])
    checks={'all_completed':all(t['status']=='completed' for t in tasks),
            'one_claim_each':all(t['claim_count']==1 for t in tasks) and Counter(t for t,e in claims)==Counter(ids),
            'two_workers_used':len({e['payload']['worker_id'] for t,e in claims})==2,
            'overlap_observed':overlap,'leases_cleared':all(t['lease_token'] is None and t['lease_expires_at'] is None for t in tasks),
            'worker_exit_zero':all(p.returncode==0 for p in children),'sampler_finished':not sampler.is_alive()}
    peak=max(s['total_including_sampler'] for s in samples)
    summary={'configuration':FINAL_CONFIG,'model_kind':'real configured model','requested_model':os.getenv('OPENAI_MODEL'),
             'embedding':identity,'tasks':tasks,'worker_pids':[p.pid for p in children],'wall_ms':elapsed,'checks':checks,'passed':all(checks.values()),
             'database':{'max_connections':limit,'superuser_reserved':reserved,'sample_period_s':.05,'sample_count':len(samples),
                         'baseline':samples[0],'sampled_peak_client_connections_including_sampler':peak,
                         'peak_by_role':{role:max(s['counts'].get(role,0) for s in samples) for role in {r for s in samples for r in s['counts']}},
                         'samples':samples,'limitation':'sampled peak, not an exact instantaneous upper bound; this only validates two workers'},
             'claim_scope':'Both processes compete for identical six task IDs using production FOR UPDATE SKIP LOCKED; unrelated task IDs excluded.'}
    publish('concurrency',summary)
    if not summary['passed']:raise AssertionError('Concurrency checks failed; receipt retained')


class ModelFixture:
    def __init__(self,scenario,mcp_process=None):
        self.scenario=scenario;self.calls=[];self.mcp_process=mcp_process;self.agent_calls=0;self.injected=False
        fixture=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                is_json=body.get('response_format',{}).get('type')=='json_object'
                if not is_json:fixture.agent_calls+=1
                status=429 if fixture.scenario=='429_exhausted' or (fixture.scenario=='429_recovered' and not is_json and fixture.agent_calls<=2) else 200
                fixture.calls.append({'elapsed_s':time.perf_counter()-fixture.started,'status':status,'role':'preference_extractor' if is_json else 'agent'})
                if status==429:
                    payload={'error':{'message':'Controlled rate limit fixture','type':'rate_limit_error','code':'rate_limit'}}
                else:
                    message={'role':'assistant','content':None}
                    if is_json:message['content']='{"preferences":[]}'
                    elif fixture.scenario=='mcp_midway':
                        if fixture.agent_calls==2:
                            # The first SQL has already returned to the model.
                            fixture.mcp_process.kill();fixture.mcp_process.wait(timeout=5);fixture.injected=True
                        name='run_sql';args={'sql':'SELECT COUNT(*) AS orders FROM orders' if fixture.agent_calls==1 else 'SELECT COUNT(*) AS customers FROM customers'}
                        message['tool_calls']=[{'id':'fixture-'+str(fixture.agent_calls),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]
                    else:
                        message['tool_calls']=[{'id':'fixture-final','type':'function','function':{'name':'final_answer','arguments':json.dumps({'answer':'受控重试已经恢复。','claims':[]},ensure_ascii=False)}}]
                    payload={'id':'controlled-fixture','object':'chat.completion','created':0,'model':'step10-http-fixture','choices':[{'index':0,'message':message,'finish_reason':'stop' if is_json else 'tool_calls'}],
                             'usage':{'prompt_tokens':0,'completion_tokens':0,'total_tokens':0}}
                encoded=json.dumps(payload).encode()
                self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(encoded)));self.end_headers();self.wfile.write(encoded)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.started=time.perf_counter()
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}/v1'
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join(timeout=3)


def start_private_mcp():
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    proc=subprocess.Popen([sys.executable,'-m','mcp_olist.server'],env={**os.environ,'MCP_PORT':str(port)},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            with socket.create_connection(('127.0.0.1',port),timeout=.1):return proc,f'http://127.0.0.1:{port}/mcp'
        except OSError:time.sleep(.1)
    proc.kill();proc.wait();raise RuntimeError('Private real MCP did not start')


def fault(scenario):
    mcp=None;fixture=None;old=dict(os.environ);started=time.perf_counter()
    try:
        os.environ.update(FINAL_CONFIG)
        if scenario=='vector_down':
            # Caller stops the real embeddings container before invoking this.
            # Verify its endpoint actually refuses a connection; no chat needed.
            import httpx
            base=os.getenv('EMBEDDING_BASE_URL','http://embeddings:8002/v1')
            try:
                httpx.get(base.replace('/v1','')+'/health',timeout=2).raise_for_status()
            except httpx.ConnectError:pass
            else:raise AssertionError('Vector outage was not active')
        else:
            if scenario=='mcp_midway':
                mcp,url=start_private_mcp();os.environ['MCP_URL']=url
            fixture=ModelFixture(scenario,mcp)
            os.environ.update(OPENAI_BASE_URL=fixture.url,OPENAI_MODEL='step10-http-fixture',OPENAI_API_KEY='fixture-only-no-secret')
        ids=create_tasks(['工程故障测试：请分别查询订单总数和客户总数。'],FINAL_CONFIG)
        job=claim(ids[0]);process(job)
        tasks=read_tasks(ids);task=tasks[0]
        events=task['events'];calls=[e for e in events if e['type']=='model_call']
        checks={'terminal':task['status'] in {'failed','completed'},'lease_cleared':task['lease_token'] is None and task['lease_expires_at'] is None,
                'not_reclaimed':claim(ids[0]) is None,'one_claim':task['claim_count']==1}
        if scenario=='vector_down':checks.update(failed_closed=task['status']=='failed',no_chat_calls=len(calls)==0)
        elif scenario=='429_recovered':checks.update(recovered=task['status']=='completed',two_429_before_success=[c['status'] for c in fixture.calls[:3]]==[429,429,200])
        elif scenario=='429_exhausted':checks.update(failed_closed=task['status']=='failed',agent_attempts_bounded=sum(c['role']=='agent' for c in fixture.calls)==4)
        else:
            with psycopg.connect(**db_kwargs('agent','app')) as db:count=db.execute('SELECT count(*) FROM query_results WHERE task_id=%s',(ids[0],)).fetchone()[0]
            checks.update(real_mcp_killed=fixture.injected and mcp.returncode is not None,first_sql_persisted=count==1,failed_closed=task['status']=='failed')
        summary={'scenario':scenario,'configuration':FINAL_CONFIG,'task':task,'checks':checks,'passed':all(checks.values()),
                 'wall_ms':(time.perf_counter()-started)*1000,'http_attempts':fixture.calls if fixture else [],
                 'model_kind':'controlled HTTP fixture (synthetic zero usage; not model quality or cost evidence)' if fixture else 'no chat model called',
                 'transport':'production worker, subprocess runtime, SDK and real MCP/DB; private real MCP process killed mid-task' if scenario=='mcp_midway' else 'production worker, subprocess runtime, SDK and real MCP/DB',
                 'embedding_model':os.getenv('EMBEDDING_MODEL'),'embedding_revision':os.getenv('EMBEDDING_REVISION')}
        publish('fault_'+scenario,summary)
        if not summary['passed']:raise AssertionError('Fault expectations failed; evidence retained')
    finally:
        if fixture:fixture.close()
        if mcp and mcp.poll() is None:mcp.kill();mcp.wait()
        os.environ.clear();os.environ.update(old)


def main():
    p=argparse.ArgumentParser();p.add_argument('--concurrency',action='store_true');p.add_argument('--worker');p.add_argument('--ids');p.add_argument('--fault',choices=['vector_down','mcp_midway','429_recovered','429_exhausted']);a=p.parse_args()
    if a.worker:worker(a.ids.split(','),a.worker)
    elif a.concurrency or a.fault:
        # Serialize resource measurements and destructive fault experiments with
        # eval/run.py. Worker children do not acquire this parent-held lock.
        with psycopg.connect(**db_kwargs('agent','app'),autocommit=True) as lock:
            if not lock.execute('SELECT pg_try_advisory_lock(730018)').fetchone()[0]:
                raise RuntimeError('Another evaluation is running; do not overlap experiments')
            if a.concurrency:concurrency()
            else:fault(a.fault)
    else:p.error('Choose experiment')


if __name__=='__main__':main()
