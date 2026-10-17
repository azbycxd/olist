"""Local real-worker SIGKILL demonstration; never changes unrelated containers.

Create a test account and task in the UI first, save test credentials in ignored
logs/demo_credentials.json, then confirm a plan with sequential subtasks.
This host-side recorder kills only this Compose project's worker after a checked
subtask is complete, restarts it, and verifies checkpoint reuse through the API.
"""
import hashlib
import argparse
import json
import re
import subprocess
import time
import urllib.request
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE='http://localhost:8000'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--resume-log',type=Path,help='Continue a recorded kill if the restart command failed')
    args=parser.parse_args()
    credentials=json.loads((ROOT/'logs/demo_credentials.json').read_text(encoding='utf-8'))
    def call(path,body=None,token=None):
        req=urllib.request.Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,
            headers={**({'Authorization':'Bearer '+token} if token else {}),'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)
    token=call('/login',credentials)['access_token']
    tasks=call('/tasks',token=token)['tasks']
    recorded=None
    if args.resume_log:
        path=args.resume_log.resolve()
        if not path.is_relative_to(ROOT/'logs'):raise ValueError('Recorder path must be inside logs/')
        records=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        recorded=next(e for e in reversed(records) if e['event']=='before_kill')
        task=next(t for t in tasks if t['task_id']==recorded['task']['task_id'])
    else:task=next(t for t in tasks if t['status'] in {'pending','planning','awaiting_confirmation','running'})
    ident=task['task_id'];stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    if not recorded:path=ROOT/'logs'/f'resume_demo_{stamp}.jsonl'
    def record(kind,**payload):
        data={'at':datetime.now(timezone.utc).isoformat(),'event':kind,**payload}
        with path.open('a',encoding='utf-8') as stream:stream.write(json.dumps(data,ensure_ascii=False)+'\n')
        print(kind,flush=True)
    deadline=time.monotonic()+600
    if recorded:
        completed={k:recorded['task']['subtasks'][k] for k in recorded['completed_ids']}
        pending={k:recorded['task']['subtasks'][k] for k in recorded['unfinished_ids']}
        record('restart_retry',reason='Prior compose start traversed dependencies and failed at the old init-data container; preserving this same kill checkpoint')
    else:
        record('demo_started',task_id=ident,scope='Only this Compose project worker; actual API and model, no tool stubs')
        while time.monotonic()<deadline:
            task=call('/tasks/'+ident,token=token)
            completed={k:p for k,p in task['subtasks'].items() if p['status']=='completed' and p['review'] and all(d['approved'] for d in p['review'])}
            pending={k:p for k,p in task['subtasks'].items() if k not in completed}
            if task['status']=='running' and completed and pending:break
            if task['status'] in {'failed','completed'}:raise RuntimeError('Task ended before kill checkpoint')
            time.sleep(.15)
        else:raise TimeoutError('No completed subtask checkpoint observed')
        record('before_kill',task=task,completed_ids=sorted(completed),unfinished_ids=sorted(pending))
        result=subprocess.run(['docker','compose','kill','-s','SIGKILL','worker'],cwd=ROOT,capture_output=True,text=True)
        if result.returncode:raise RuntimeError('Worker kill failed')
        record('worker_killed',returncode=result.returncode)
        time.sleep(8)
    restart=['docker','compose','up','-d','--no-deps','worker']
    result=subprocess.run(restart,cwd=ROOT,capture_output=True,text=True)
    if result.returncode:
        record('restart_failed',returncode=result.returncode)
        raise RuntimeError('Worker restart failed')
    record('worker_restarted',returncode=result.returncode,command=restart)
    while time.monotonic()<deadline:
        final=call('/tasks/'+ident,token=token)
        if final['status'] in {'completed','failed'}:break
        time.sleep(.5)
    else:raise TimeoutError('Recovery did not finish')
    req=urllib.request.Request(BASE+'/tasks/'+ident+'/events',headers={'Authorization':'Bearer '+token})
    with urllib.request.urlopen(req,timeout=30) as response:raw=response.read().decode()
    events=[]
    for frame in raw.split('\n\n'):
        lines=frame.splitlines();data=next((l[6:] for l in lines if l.startswith('data: ')),None)
        seq=next((int(l[4:]) for l in lines if l.startswith('id: ')),None)
        if data and seq:events.append({'seq':seq,**json.loads(data)})
    cursor=events[len(events)//2]['seq']
    req=urllib.request.Request(BASE+'/tasks/'+ident+'/events',headers={'Authorization':'Bearer '+token,'Last-Event-ID':str(cursor)})
    with urllib.request.urlopen(req,timeout=30) as response:replayed=response.read().decode()
    reconnect_ids=[int(n) for n in re.findall(r'^id: (\d+)$',replayed,re.M)]
    reconnect_verified=reconnect_ids==[e['seq'] for e in events if e['seq']>cursor]
    recover=next(e for e in events if e['type']=='worker_claimed' and e['payload']['recovered'])
    after=[e for e in events if e['seq']>recover['seq']]
    reused={i for e in after if e['type']=='subtasks_reused' for i in e['payload']['subtask_ids']}
    rerun={e['payload']['subtask_id'] for e in after if e['type']=='subtask_started'}
    preserved=all(final['subtasks'][k]['claims']==p['claims'] and final['subtasks'][k]['review']==p['review'] for k,p in completed.items())
    verified=final['status']=='completed' and set(completed)<=reused and not set(completed)&rerun and preserved
    summary={'task_id':ident,'final_status':final['status'],'completed_before_kill':sorted(completed),
        'unfinished_before_kill':sorted(pending),'reused_after_restart':sorted(reused),'executed_after_restart':sorted(rerun),
        'completed_claims_and_evidence_unchanged':preserved,'verified':verified and reconnect_verified,'usage':final['usage'],
        'sse_reconnect':{'last_event_id':cursor,'received_ids':reconnect_ids,'verified':reconnect_verified},
        'embedding':final['embedding'],'event_count':len(events),'events':events,'source_log':path.name}
    record('demo_summary',**summary)
    summary['source_log_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    evidence=ROOT/'evidence'/(path.stem+'.summary.json')
    with evidence.open('x',encoding='utf-8') as stream:json.dump(summary,stream,ensure_ascii=False,indent=2)
    (ROOT/'logs/demo_task.json').write_text(json.dumps({'task_id':ident,'evidence':evidence.name}),encoding='utf-8')
    print('Evidence:',evidence.name,flush=True)
    if not verified or not reconnect_verified:raise AssertionError('Checkpoint reuse failed; inspect preserved evidence')


if __name__=='__main__':main()
