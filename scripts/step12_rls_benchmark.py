"""Read-only C/D/E dev SQL workload; no model, scoring, or holdout execution."""
import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path
from time import perf_counter
import psycopg
from config import db_kwargs
from eval.dataset import load_questions


def run(phase):
    target=Path(f'evidence/step12_c2_rls_{phase}.json')
    log=Path(f'logs/step12_c2_rls_{phase}.jsonl')
    # Exclusive markers protect the declared single pass from accidental reruns.
    with target.open('x',encoding='utf-8') as f:f.write('{"status":"started"}\n')
    questions=[q for q in load_questions() if q['split']=='dev' and q['category'] in 'CDE']
    rows=[]
    with log.open('x',encoding='utf-8') as stream,psycopg.connect(**db_kwargs('olist','reader')) as conn:
        conn.execute('SET TRANSACTION READ ONLY')
        conn.execute("SET LOCAL app.allowed_states='ALL'")
        for q in questions:
            began=perf_counter();data=conn.execute(q['gold_sql']).fetchall();elapsed=(perf_counter()-began)*1000
            row={'id':q['id'],'sql_sha256':hashlib.sha256(q['gold_sql'].encode()).hexdigest(),'duration_ms':elapsed,'rows':len(data)}
            rows.append(row);stream.write(json.dumps(row)+'\n');stream.flush()
        roles=conn.execute("SELECT rolname,rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchall()
        policies=conn.execute("SELECT relname,relrowsecurity,relforcerowsecurity FROM pg_class WHERE relname IN ('customers','orders','order_items','order_payments','order_reviews') ORDER BY relname").fetchall()
    timings=sorted(r['duration_ms'] for r in rows)
    result={'kind':'固定SQL负载，无模型，无评分','phase':phase,'passes':1,'question_split':'C/D/E dev','queries':len(rows),
            'p50_ms':timings[math.ceil(.5*len(timings))-1],'p95_ms':timings[math.ceil(.95*len(timings))-1],
            'rows':rows,'role':roles,'policies':policies,'log':str(log),'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in {'rows','policies'}},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['before','after']);run(p.parse_args().phase)
