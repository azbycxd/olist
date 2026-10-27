"""One real README-example task; no evaluation questions or scores."""
import hashlib
import json
import os
from pathlib import Path
import time
from uuid import uuid4
import httpx
import psycopg
from config import db_kwargs,ROOT
from api.tasks import create_task,NewTask
from scripts.task_worker import claim,process
from eval.robustness import start_private_mcp
import telemetry

REQUIRED_SPANS={'task.create','worker.claim','worker.execute','agent.run','agent.step','mcp.call','mcp.request','sql.execute'}


def fetch_trace(trace_id):
    # Collector ingestion is asynchronous even after the SDK's force_flush.
    with httpx.Client(timeout=10) as client:
        for _ in range(50):
            response=client.get('http://jaeger:16686/api/traces/'+trace_id)
            if response.status_code==200:
                document=response.json()
                names={s['operationName'] for t in document.get('data',[]) for s in t['spans']}
                if REQUIRED_SPANS<=names:return document
            time.sleep(.2)
        raise RuntimeError('Collector did not return the complete task trace')


def export_existing():
    path=ROOT/'evidence/step12_b3_real_task.json'
    report=json.loads(path.read_text(encoding='utf8'))
    document=fetch_trace(report['trace_id'])
    target=ROOT/'evidence/step12_b3_real_trace.json'
    target.write_text(json.dumps(document,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    report['trace_sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
    report['collector_verification']='All required span types present after read-only re-fetch; no model call'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'trace_id':report['trace_id'],'spans':sum(len(t['spans']) for t in document['data']),'additional_model_calls':0}))


def run():
    question='2017 年 SP 州有多少客户？'
    assert question in (ROOT/'README.md').read_text(encoding='utf8')
    mcp,url=start_private_mcp()
    os.environ['MCP_URL']=url
    started=time.perf_counter()
    ident=None
    try:
        with psycopg.connect(**db_kwargs('agent','app')) as conn:
            owner=conn.execute("INSERT INTO users(username,data_scope) VALUES(%s,ARRAY['ALL']) RETURNING user_id",('trace-real-'+uuid4().hex,)).fetchone()[0]
        ident=create_task(NewTask(question=question),owner)['task_id']
        job=claim(ident)
        if job is None:raise RuntimeError('Real example could not be claimed; do not resubmit automatically')
        process(job)
        telemetry.flush()
    finally:
        mcp.terminate();mcp.wait(timeout=30)
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        status,error,parent=conn.execute('SELECT status,error,traceparent FROM tasks WHERE task_id=%s',(ident,)).fetchone()
        calls=conn.execute("SELECT payload->'usage',latency_ms,payload->>'error_class' FROM events WHERE task_id=%s AND type='model_call' ORDER BY seq",(ident,)).fetchall()
    trace_id=parent.split('-')[1]
    document=fetch_trace(trace_id)
    path=ROOT/'evidence/step12_b3_real_trace.json'
    path.write_text(json.dumps(document,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    from api.metrics import render
    metrics=ROOT/'evidence/step12_b3_metrics.prom';metrics.write_bytes(render())
    report={'model_kind':'真实模型；仅README示例，非holdout/评测题','task_id':ident,'question':question,
        'status':status,'error':error,'trace_id':trace_id,'elapsed_ms':(time.perf_counter()-started)*1000,
        'model_calls':[{'usage':usage,'latency_ms':latency,'error_class':error,'accounting':telemetry.usage_summary(usage)} for usage,latency,error in calls],
        'total_tokens':sum((usage or {}).get('total_tokens',0) for usage,_,_ in calls),
        'trace_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'metrics_sha256':hashlib.sha256(metrics.read_bytes()).hexdigest()}
    (ROOT/'evidence/step12_b3_real_task.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:report[k] for k in ('task_id','status','trace_id','total_tokens')},ensure_ascii=False))
    assert status=='completed',error
    names={s['operationName'] for t in document['data'] for s in t['spans']}
    assert {'task.create','worker.claim','worker.execute','agent.run','agent.step','mcp.call','mcp.request','sql.execute'}<=names,names


if __name__=='__main__':
    import sys
    if '--export-existing' in sys.argv:export_existing()
    else:run()
