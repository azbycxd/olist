"""One-shot behavioral boundary protocol, separate from scored holdout."""
import hashlib
import json
import os
import re
from time import perf_counter
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

from config import ROOT, FINAL_CONFIG, db_kwargs
from scripts.common import start_log, record
from scripts.evidence import write_evidence
from scripts.runtime import run_runtime
from eval.checker import check, DatabaseEvidence
from eval.run import usage_summary
from mcp_olist.embedding_config import provenance


def execute(suite='step10', *, tag=None, runtime_config=None):
    if suite not in {'step10','step11-original','step11-new'}:raise ValueError('Unknown boundary suite')
    source=ROOT/('eval/boundary_step11.json' if suite=='step11-new' else 'eval/boundary_cases.json')
    questions=json.loads(source.read_text(encoding='utf-8'))
    tag=tag or suite
    if not re.fullmatch(r'[A-Za-z0-9_-]+',tag):raise ValueError('Invalid boundary tag')
    configuration={**FINAL_CONFIG,**(runtime_config or {})}
    os.environ.update(configuration,SCHEMA_MODE='on_demand')
    marker=ROOT/'evidence'/f'{tag.replace("-","_")}_boundary_protocol.json'
    if marker.exists():raise ValueError('Boundary protocol already started; do not rerun for better answers')
    logger,path=start_log('eval_'+tag+'-boundary')
    identity=provenance(used=True)
    results=[];calls=[]
    with psycopg.connect(**db_kwargs('agent','app'),autocommit=True) as db, psycopg.connect(**db_kwargs(role='reader')) as data:
        if not db.execute('SELECT pg_try_advisory_lock(730018)').fetchone()[0]:raise RuntimeError('Another evaluation is running')
        with marker.open('x',encoding='utf-8') as f:
            json.dump({'source_log':path.name,'question_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                'configuration':configuration,'embedding':identity,'questions':questions,'repetitions':1,
                'scoring':'predeclared behavioral expectations, deterministic evidence audit plus explicit saved-response review; not holdout accuracy'},f,ensure_ascii=False,indent=2)
        data.execute('SET TRANSACTION READ ONLY')
        data.execute("SET LOCAL app.allowed_states='ALL'")
        version=data.execute('SELECT current_data_version()').fetchone()[0]
        def snapshot():
            return {'orders':data.execute('SELECT count(*) FROM orders').fetchone()[0],
                    'canceled_orders':data.execute("SELECT count(*) FROM orders WHERE order_status='canceled'").fetchone()[0],
                    'review_scores':data.execute('SELECT review_score,count(*) FROM order_reviews GROUP BY review_score ORDER BY review_score').fetchall()}
        before=snapshot()
        # Evaluator-only checks; neither these SQLs nor their results enter Agent input.
        boundary_facts={'min_purchase':str(data.execute('SELECT min(order_purchase_timestamp) FROM orders').fetchone()[0]),
            'max_purchase':str(data.execute('SELECT max(order_purchase_timestamp) FROM orders').fetchone()[0]),
            'negative_price_rows':data.execute('SELECT count(*) FROM order_items WHERE price<0').fetchone()[0],
            'orders_2017':data.execute("SELECT count(*) FROM orders WHERE order_purchase_timestamp>='2017-01-01' AND order_purchase_timestamp<'2018-01-01'").fetchone()[0]}
        for q in questions:
            uid=db.execute("INSERT INTO users(username,data_scope) VALUES(%s,ARRAY['ALL']) RETURNING user_id",('boundary-'+uuid4().hex,)).fetchone()[0]
            tid=db.execute("INSERT INTO tasks(user_id,question,status,run_config) VALUES(%s,%s,'running',%s) RETURNING task_id",(uid,q['question'],Jsonb(configuration))).fetchone()[0]
            row={**q,'task_id':str(tid),'events':[]};seq=0;task_calls=[]
            def emit(kind,payload,tokens=0,latency_ms=0):
                nonlocal seq
                seq+=1
                record(logger,kind,question_id=q['id'],task_id=str(tid),payload=payload,tokens=tokens,latency_ms=latency_ms)
                db.execute('INSERT INTO events(task_id,seq,type,payload,tokens,latency_ms) VALUES(%s,%s,%s,%s,%s,%s)',(tid,seq,kind,Jsonb(__import__('privacy').redact(payload)),tokens,latency_ms))
                if kind=='model_call':calls.append(payload);task_calls.append(payload)
                if kind in {'termination','tool_call','tool_result','number_gate','runtime_error','data_boundary_context','boundary_stop'}:row['events'].append({'type':kind,'payload':payload})
                if kind=='termination' and payload.get('scope')=='task':row['termination']=payload['reason']
                if kind=='context_usage':row['peak_context_tokens']=max(row.get('peak_context_tokens',0),payload['prompt_tokens'])
            started=perf_counter()
            try:
                response=run_runtime(q['question'],tid,emit)
                row['response']=response.model_dump()
                row['evidence_audit']=check(response,DatabaseEvidence(db),str(tid),version)
            except Exception as exc:row['error']=type(exc).__name__
            row['latency_ms']=(perf_counter()-started)*1000
            row['usage']=usage_summary(task_calls,None,None)
            db.execute('UPDATE tasks SET status=%s,result=%s,error=%s,updated_at=now() WHERE task_id=%s',
                ('completed' if row.get('termination')=='final_answer' else 'failed',Jsonb(row.get('response')),row.get('error') or (row.get('termination') if row.get('termination')!='final_answer' else None),tid))
            row['saved_results']=[{'result_id':str(r[0]),'sql':r[1],'row_count':r[2],'columns':r[3],'preview':r[4][:3]} for r in db.execute('SELECT result_id,sql,row_count,columns,rows FROM query_results WHERE task_id=%s ORDER BY created_at',(tid,)).fetchall()]
            record(logger,'boundary_result',**row);results.append(row)
        summary={'kind':'boundary_behavior_not_holdout','suite':suite,'configuration':configuration,'schema_mode':'on_demand','embedding':identity,
                 'data_version':version,'questions_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                 'cases':results,'usage':usage_summary(calls,None,None),'requested_model':os.getenv('OPENAI_MODEL'),
                 'before':before,'after':snapshot(),'evaluator_boundary_facts':boundary_facts,
                 'source_log':path.name,'behavior_review':'pending; see separate review receipt',
                 'runtime_sha256':{str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in [*sorted((ROOT/'agent').glob('*.py')),ROOT/'scripts/runtime.py']}}
        record(logger,'boundary_summary',**summary)
        summary['source_log_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        receipt=write_evidence(path.stem+'.summary.json',summary)
        print('Evidence:',receipt.name)
        return summary
