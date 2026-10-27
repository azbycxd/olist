"""Model doubles only: isolated API/MCP/workers, real PostgreSQL and SSE."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time
from uuid import uuid4
import httpx
import psycopg
from psycopg.types.json import Jsonb
import config
from config import ROOT,db_kwargs


def percentile(values,p):
    values=sorted(values)
    if not values:return None
    position=(len(values)-1)*p;lower=int(position);upper=min(lower+1,len(values)-1)
    return values[lower]+(values[upper]-values[lower])*(position-lower)


def summarize(tasks,elapsed):
    waits=[t['queue_seconds'] for t in tasks if t.get('queue_seconds') is not None]
    completed=sum(t['status']=='completed' for t in tasks)
    return {'completed':completed,'success_rate':completed/len(tasks) if tasks else None,
            'throughput_tasks_per_minute':completed*60/elapsed,
            'queue_wait_p50_seconds':percentile(waits,.5),'queue_wait_p95_seconds':percentile(waits,.95),
            'queue_wait_observed_count':len(waits),
            'error_types':dict(Counter(t.get('error') or t['status'] for t in tasks if t['status']!='completed'))}


def verify_load(value):
    assert value['workers']==4 and value['task_count']==100 and value['sse_peak']>=100


def write_report(name,payload,observations,*,directory=ROOT/'evidence'):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    raw=directory/('step12_chaos_'+name+'.jsonl')
    raw.write_text(''.join(json.dumps(row,ensure_ascii=False,default=str)+'\n' for row in observations),encoding='utf8')
    report={'model_kind':'模型替身',**payload,'source_log':raw.name,'source_log_sha256':hashlib.sha256(raw.read_bytes()).hexdigest()}
    text=json.dumps(report,ensure_ascii=False,indent=2,default=str).replace('{\n  "model_kind": "模型替身",','{"model_kind": "模型替身",',1)+'\n'
    path=directory/('step12_chaos_'+name+'.json');path.write_text(text,encoding='utf8')
    return path


def free_port():
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));return sock.getsockname()[1]


def source_commit():
    try:return subprocess.check_output(['git','rev-parse','HEAD'],text=True,stderr=subprocess.DEVNULL).strip()
    except (OSError,subprocess.CalledProcessError):return None


def read_tasks(ids):
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        rows=conn.execute("""SELECT t.task_id,t.status,t.error,t.claim_count,t.provider_requeues,
            EXTRACT(EPOCH FROM((SELECT min(e.created_at) FROM events e WHERE e.task_id=t.task_id AND e.type='worker_claimed')-t.created_at))
            FROM tasks t WHERE t.task_id=ANY(%s::uuid[])""",(ids,)).fetchall()
    return [dict(zip(['task_id','status','error','claim_count','provider_requeues','queue_seconds'],
                     [str(row[0]),*row[1:5],float(row[5]) if row[5] is not None else None])) for row in rows]


class ModelDouble:
    def __init__(self,delay=1,pause_until=None):
        self.calls=[];self.started=threading.Event();lock=threading.Lock();outer=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                with lock:outer.calls.append({'at':time.monotonic(),'status':200,'actual_tokens':1000})
                outer.started.set()
                if pause_until is not None:
                    deadline=time.monotonic()+60
                    while not pause_until.exists() and time.monotonic()<deadline:time.sleep(.05)
                time.sleep(delay)
                has_result=any(m.get('role')=='tool' and 'result_id' in (m.get('content') or '') for m in body['messages'])
                name='final_answer' if has_result else 'run_sql'
                args={'answer':'模型替身完成','claims':[]} if has_result else {'sql':'SELECT count(*) AS n FROM orders'}
                payload={'id':'chaos-fixture','object':'chat.completion','created':0,'model':'chaos-fixture',
                         'choices':[{'index':0,'finish_reason':'tool_calls','message':{'role':'assistant','content':None,
                         'tool_calls':[{'id':uuid4().hex,'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}}],
                         'usage':{'prompt_tokens':900,'completion_tokens':100,'total_tokens':1000}}
                data=json.dumps(payload).encode()
                try:
                    self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
                except (BrokenPipeError,ConnectionResetError):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.daemon_threads=True
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.url=f'http://127.0.0.1:{self.server.server_port}/v1'

    def close(self):self.server.shutdown();self.server.server_close()


def run(mode,label=None):
    from api.memories import issue
    source_hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
                   ['scripts/step12_chaos.py','scripts/task_worker.py','db_pool.py','api/tasks.py','mcp_olist/service.py']}
    count,workers=(100,4) if mode=='load' else (1,2) if mode=='db_restart' else (5,2)
    signal_file=ROOT/'logs/step12_chaos_db_signal.json'
    if mode=='db_restart':
        signal_file.unlink(missing_ok=True)
        (ROOT/'logs/step12_chaos_db_restart_ready.json').unlink(missing_ok=True)
    fixture=ModelDouble(delay=4 if mode=='db_restart' else 1,pause_until=signal_file if mode=='db_restart' else None)
    tag=mode+'_'+uuid4().hex[:8];observations=[];children=[];handles=[];stop=threading.Event()
    stream_pool=None;ids=[];streams=[];sampler=None;all_open=threading.Event();sse_lock=threading.Lock()
    sse={'active':0,'peak':0,'errors':[]};samples=[];health=[];worker_exits=[];process_logs=[]
    env={**os.environ,'OLIST_LOAD_DOTENV':'0','OPENAI_BASE_URL':fixture.url,'OPENAI_MODEL':'chaos-'+uuid4().hex,
         'OTEL_EXPORTER_OTLP_ENDPOINT':'','PROVIDER_RPM':'','PROVIDER_TPM':'','PROVIDER_MAX_INFLIGHT':'0'}
    for key in ('DEEPSEEK_MODEL','DEEPSEEK_BASE_URL','DEEPSEEK_API_KEY'):env.pop(key,None)
    api_port,mcp_port=free_port(),free_port()
    api_url=f'http://127.0.0.1:{api_port}';mcp_url=f'http://127.0.0.1:{mcp_port}'
    env['MCP_URL']=mcp_url+'/mcp'
    def start(name,args,environment):
        path=ROOT/'logs'/('step12_chaos_'+tag+'_'+name+'.txt');handle=path.open('w',encoding='utf8');handles.append(handle);process_logs.append(path)
        child=subprocess.Popen([sys.executable,*args],env=environment,stdout=handle,stderr=handle,start_new_session=True)
        children.append(child);return child
    proxy=mode in {'network_baseline','latency','packet_loss'}
    proxy_client=httpx.Client(base_url='http://toxiproxy:8474',timeout=5) if proxy else None
    toxic_active=False;injection_started=None;injection_ended=None
    started=time.monotonic()
    try:
        if proxy:
            existing=proxy_client.get('/proxies/step12_olist')
            if existing.status_code==200:proxy_client.delete('/proxies/step12_olist').raise_for_status()
            proxy_client.post('/proxies',json={'name':'step12_olist','listen':'0.0.0.0:8666','upstream':'db:5432'}).raise_for_status()
        mcp_env={**env,'MCP_PORT':str(mcp_port),**({'PGHOST':'toxiproxy','PGPORT':'8666'} if proxy else {})}
        mcp=start('mcp',['-m','mcp_olist.server'],mcp_env)
        api=start('api',['-m','uvicorn','api.tasks:app','--host','127.0.0.1','--port',str(api_port),'--no-access-log'],env)
        with httpx.Client(timeout=15,limits=httpx.Limits(max_connections=150,max_keepalive_connections=100)) as client:
            for _ in range(100):
                try:
                    if client.get(api_url+'/readyz').status_code==200 and client.get(mcp_url+'/readyz').status_code==200:break
                except httpx.HTTPError:pass
                if api.poll() is not None or mcp.poll() is not None:raise RuntimeError('Fixture service exited during startup')
                time.sleep(.1)
            else:raise TimeoutError('Fixture services did not become ready')
            with psycopg.connect(**db_kwargs('agent','app')) as conn:
                owners=[conn.execute('INSERT INTO users(username) VALUES(%s) RETURNING user_id',('chaos-'+uuid4().hex,)).fetchone()[0] for _ in range(count)]
            tokens=[issue(owner) for owner in owners]
            submitted=time.monotonic()
            def submit(token):
                response=client.post(api_url+'/tasks',headers={'Authorization':'Bearer '+token},json={'question':'工程故障演练，模型替身'})
                response.raise_for_status();return response.json()['task_id']
            with ThreadPoolExecutor(max_workers=count) as pool:ids=list(pool.map(submit,tokens))
            with psycopg.connect(**db_kwargs('agent','app')) as conn:
                conn.execute('UPDATE tasks SET run_config=run_config||%s WHERE task_id=ANY(%s::uuid[])',(Jsonb({'RAG_MODE':'off','USE_MEMORY':'false'}),ids))
            def stream(pair):
                ident,token=pair;opened=False;events=0
                try:
                    # Shared thread-safe client avoids constructing 100 SSL contexts.
                    with client.stream('GET',api_url+f'/tasks/{ident}/events',headers={'Authorization':'Bearer '+token},timeout=350) as response:
                        response.raise_for_status()
                        with sse_lock:
                            opened=True;sse['active']+=1;sse['peak']=max(sse['peak'],sse['active'])
                            if sse['active']==count:all_open.set()
                        for line in response.iter_lines():
                            if line.startswith('event:'):events+=1
                except Exception as exc:
                    with sse_lock:sse['errors'].append(type(exc).__name__)
                finally:
                    if opened:
                        with sse_lock:sse['active']-=1
                return events
            stream_pool=ThreadPoolExecutor(max_workers=count);streams=[stream_pool.submit(stream,pair) for pair in zip(ids,tokens)]
            if not all_open.wait(20):raise RuntimeError('Not all SSE connections opened before worker launch')
            if mode in {'latency','packet_loss'}:
                toxic={'name':'step12_fault','type':mode,'stream':'downstream','toxicity':1,
                       'attributes':{'latency':500,'jitter':0} if mode=='latency' else {'loss_rate':.1,'correlation':0}}
                response=proxy_client.post('/proxies/step12_olist/toxics',json=toxic);response.raise_for_status()
                observations.append({'toxic':response.json()});toxic_active=True;injection_started=time.monotonic()
            worker_processes=[start('worker'+str(n),['-m','scripts.service_load','worker','--ids',','.join(ids)],{**env,'WORKER_ID':'chaos-'+tag+'-'+str(n)}) for n in range(workers)]
            def sample():
                conn=None
                with httpx.Client(timeout=3) as observer:
                    while not stop.is_set():
                        now=time.monotonic()
                        try:
                            if conn is None:conn=psycopg.connect(**db_kwargs('agent'),autocommit=True)
                            counts=dict(conn.execute("SELECT application_name,count(*) FROM pg_stat_activity WHERE application_name LIKE 'olist:%%' GROUP BY application_name").fetchall())
                            clients=conn.execute("SELECT count(*) FROM pg_stat_activity WHERE backend_type='client backend'").fetchone()[0]
                            samples.append({'at':now,'total':sum(counts.values()),'database_all_client_connections':clients,'counts':counts})
                        except Exception as exc:
                            observations.append({'at':now,'observer_db_error':type(exc).__name__})
                            if conn:conn.close();conn=None
                        if mode=='db_restart':
                            statuses={}
                            for name,url in [('api',api_url),('mcp',mcp_url)]:
                                for path in ('healthz','readyz'):
                                    try:statuses[name+'_'+path]=observer.get(url+'/'+path).status_code
                                    except httpx.HTTPError as exc:statuses[name+'_'+path]=type(exc).__name__
                            health.append({'at':time.monotonic(),'unix_seconds':time.time(),**statuses})
                        stop.wait(.05 if mode=='load' else .1)
                if conn:conn.close()
            sampler=threading.Thread(target=sample,daemon=True);sampler.start()
            if mode=='db_restart':
                assert fixture.started.wait(20)
                (ROOT/'logs/step12_chaos_db_restart_ready.json').write_text(json.dumps({'task_ids':ids,'at':time.monotonic(),'unix_seconds':time.time(),'api_url':api_url,'mcp_url':mcp_url}),encoding='utf8')
            deadline=time.monotonic()+340
            while time.monotonic()<deadline:
                if mode=='packet_loss' and toxic_active and time.monotonic()-injection_started>=45:
                    proxy_client.delete('/proxies/step12_olist/toxics/step12_fault').raise_for_status();toxic_active=False;injection_ended=time.monotonic()
                try:tasks=read_tasks(ids)
                except psycopg.Error as exc:
                    observations.append({'at':time.monotonic(),'task_read_error':type(exc).__name__});time.sleep(.2);continue
                if all(t['status'] in {'completed','failed','canceled'} for t in tasks):break
                exited=[(n,p.returncode) for n,p in enumerate(worker_processes) if p.poll() is not None]
                if exited:
                    worker_exits=exited
                    # Capture states without simulating compose's restart policy.
                    if len(exited)==workers:break
                time.sleep(.2)
            elapsed=time.monotonic()-submitted
            if mode=='db_restart':
                # Continue observing pool readiness after the task terminates.
                for _ in range(40):
                    if health and health[-1].get('api_readyz')==health[-1].get('mcp_readyz')==200 and len(health)>=10:break
                    time.sleep(.2)
            for future in streams:
                if future.done():future.result()
            stop.set();sampler.join(timeout=10)
            with psycopg.connect(**db_kwargs('agent','app')) as conn:
                sql_times=[float(row[0]) for row in conn.execute("SELECT latency_ms FROM events WHERE task_id=ANY(%s::uuid[]) AND type='sql_execution'",(ids,))]
                error_rows=conn.execute("SELECT type,payload->>'error' FROM events WHERE task_id=ANY(%s::uuid[]) AND payload ? 'error'",(ids,)).fetchall()
                tool_events=conn.execute("SELECT type,count(*) FROM events WHERE task_id=ANY(%s::uuid[]) AND type IN ('tool_call','mcp_call','mcp_result') GROUP BY type",(ids,)).fetchall()
            cap=config.API_POOL_MAX+config.MCP_AGENT_POOL_MAX+config.MCP_OLIST_POOL_MAX+workers*(config.WORKER_AGENT_POOL_MAX+config.WORKER_OLIST_POOL_MAX)
            result={'workers':workers,'task_count':count,'sse_peak':sse['peak'],'sse_errors':sse['errors'],
                'elapsed_seconds':elapsed,**summarize(tasks,elapsed),'connection_peak':max((x['total'] for x in samples),default=0),
                'connection_cap':cap,'connection_cap_formula':'API + MCP agent + MCP olist + workers * (worker agent + worker olist)',
                'database_all_client_peak':max((x['database_all_client_connections'] for x in samples),default=0),
                'connection_sampling_interval_seconds':.05 if mode=='load' else .1,
                'sql_count':len(sql_times),'sql_mean_ms':sum(sql_times)/len(sql_times) if sql_times else None,'sql_p95_ms':percentile(sql_times,.95),
                'model_requests':len(fixture.calls),'model_tokens':1000*len(fixture.calls),'worker_exits':worker_exits,
                'injection_seconds':((injection_ended or time.monotonic())-injection_started) if injection_started else 0,
                'tool_event_counts':dict(tool_events),'tool_error_types':dict(Counter(error for kind,error in error_rows if error)),
                'tasks':tasks,'conclusion':'待依据实测审查；此为模型替身，不表示真实模型性能或质量。','changed_code':False,
                'source_commit':source_commit(),
                'source_hashes':source_hashes,'source_hash_capture':'run_start'}
            if mode=='load':verify_load(result)
            observations.extend([{'connection_sample':x} for x in samples]);observations.extend([{'health_sample':x} for x in health]);observations.extend([{'model_call':x} for x in fixture.calls])
            if proxy:observations.append({'proxy_metrics':proxy_client.get('/metrics').text})
            path=write_report(label or mode,result,observations)
            print(json.dumps({'receipt':path.name,**{k:result[k] for k in ('completed','task_count','sse_peak','elapsed_seconds','connection_peak','error_types')}},ensure_ascii=False),flush=True)
    finally:
        stop.set()
        if proxy_client:
            if toxic_active:proxy_client.delete('/proxies/step12_olist/toxics/step12_fault')
            proxy_client.close()
        for p in children:
            if p.poll() is None:p.terminate()
        for p in children:
            try:p.wait(timeout=25)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
        fixture.close()
        if stream_pool:stream_pool.shutdown(wait=False,cancel_futures=True)
        for handle in handles:handle.close()
        if 'path' in locals():
            value=json.loads(path.read_text(encoding='utf8'))
            value['process_logs']=[{'path':p.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in process_logs]
            text=json.dumps(value,ensure_ascii=False,indent=2).replace('{\n  "model_kind": "模型替身",','{"model_kind": "模型替身",',1)+'\n';path.write_text(text,encoding='utf8')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['load','db_restart','network_baseline','latency','packet_loss'])
    parser.add_argument('--label',help='Separate receipt name; preserve previous observations')
    args=parser.parse_args();run(args.mode,args.label)
