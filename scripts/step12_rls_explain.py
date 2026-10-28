"""Explain the five slowest archived SQLs on an isolated copy, never the live DB."""
import hashlib
import json
from pathlib import Path
import psycopg
from config import db_kwargs
from eval.dataset import load_questions


def main():
    database = 'step12_rls_diag'
    archived = json.loads(Path('evidence/step12_c2_rls_after.json').read_text())
    ids = [r['id'] for r in sorted(archived['rows'], key=lambda r:r['duration_ms'], reverse=True)[:5]]
    questions = {q['id']:q for q in load_questions() if q['split']=='dev'}
    target = Path('evidence/step12_c2_explain_plans.json')
    with target.open('x') as stream: stream.write('{"status":"started"}\n')
    rows = []
    for phase, action in [('before_rls','DISABLE'), ('original_rls','ENABLE')]:
        with psycopg.connect(**db_kwargs(database)) as admin:
            for table in ('customers','orders','order_items','order_payments','order_reviews'):
                admin.execute(f'ALTER TABLE {table} {action} ROW LEVEL SECURITY')
        with psycopg.connect(**db_kwargs(database,'reader')) as conn:
            conn.execute('SET TRANSACTION READ ONLY')
            conn.execute("SET LOCAL app.allowed_states='ALL'")
            for ident in ids:
                query=questions[ident]['gold_sql']
                plan=conn.execute('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) '+query).fetchone()[0][0]
                rows.append({'phase':phase,'id':ident,'sql_sha256':hashlib.sha256(query.encode()).hexdigest(),'plan':plan})
                print(phase,ident,'execution_ms',plan['Execution Time'],'jit',plan.get('JIT',{}),flush=True)
    target.write_text(json.dumps({'database':database,'role':'agent_ro','scope':'ALL','selection':ids,'rows':rows},ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
