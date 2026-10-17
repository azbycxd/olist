"""Publish an interrupted evaluation's partial evidence without inventing metrics."""
import argparse
import json
from pathlib import Path
from uuid import UUID
import psycopg
from config import ROOT,db_kwargs
from scripts.common import record,start_log
from scripts.evidence import publish_log

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source');parser.add_argument('--reason',required=True);args=parser.parse_args()
    source=Path(args.source).resolve()
    if source.parent!=(ROOT/'logs').resolve():raise ValueError('Source must be a project log')
    rows=[json.loads(l) for l in source.read_text(encoding='utf-8').splitlines() if l.strip()]
    started=next(r for r in rows if r['event']=='run_started')
    run_id=str(UUID(started['run_id']))
    if any(r['event']=='run_summary' for r in rows):raise ValueError('Run already completed')
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        changed=conn.execute("UPDATE tasks SET status='failed',updated_at=now() WHERE status='running' AND user_id IN (SELECT user_id FROM users WHERE username LIKE %s) RETURNING task_id",('eval-'+run_id+'-%',)).fetchall()
    with source.open('a',encoding='utf-8',newline='\n') as stream:
        stream.write(json.dumps({'event':'run_interrupted','run_id':run_id,'reason':args.reason,'completed_cases':sum(r['event']=='eval_result' for r in rows),'failed_running_tasks':[str(r[0]) for r in changed],'aggregate_metrics':None},ensure_ascii=False)+'\n')
    print('Evidence:',publish_log(source).name)
