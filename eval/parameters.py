"""Offline measurement of existing traces; never imports a model client."""
import hashlib
import itertools
import json
import math
import re
from collections import defaultdict

from config import ROOT, FINAL_CONFIG, db_kwargs
from scripts.common import start_log, record
from scripts.evidence import write_evidence


def distribution(values):
    present=sorted(v for v in values if v is not None and math.isfinite(v))
    def percentile(p):
        return present[max(0,math.ceil(len(present)*p)-1)] if present else None
    return {'n':len(present),'missing':len(values)-len(present),'p50':percentile(.5),
            'p95':percentile(.95),'max':max(present) if present else None}


def collect():
    sources=[]; cases=[]; seen=set(); findings=[]; task_questions={}; finding_tasks=[]
    for path in sorted((ROOT/'evidence').glob('eval_*.summary.json')):
        s=json.loads(path.read_text(encoding='utf-8'))
        if not s.get('cases') or s.get('adapter')!='single' or s.get('recheck_only'):continue
        # Freeze historical scope: Step 10 runs must never enter this analysis.
        if s.get('tag','').startswith('step10'):continue
        log=ROOT/'logs'/s['source_log']
        if not log.is_file():raise ValueError('Missing historical log: '+log.name)
        digest=hashlib.sha256(log.read_bytes()).hexdigest()
        if digest!=s['source_log_sha256']:raise ValueError('Historical log hash mismatch: '+log.name)
        records=[json.loads(line) for line in log.read_text(encoding='utf-8').splitlines() if line.strip()]
        by_task=defaultdict(list)
        for item in records:
            if item.get('task_id'):by_task[item['task_id']].append(item)
        source={'receipt':path.name,'source_log':log.name,'source_log_sha256':digest,
                'configuration':{k:s.get(k) for k in ('tag','agent_mode','rag_mode','use_memory','number_gate','context_strategy','context_limit','token_budget')}}
        sources.append(source)
        for c in s['cases']:
            task=c['task_id'];task_questions[task]=c['question_id']
            if task in seen:continue
            seen.add(task)
            trace=by_task[task];sql=[]
            for event in trace:
                p=event.get('payload',{})
                if event['event']=='tool_result' and p.get('name')=='run_sql':
                    # row_count precedes the preview. Extract its unambiguous
                    # metadata field even if a long preview truncated the JSON.
                    raw=p.get('output_summary','')
                    match=re.search(r'"row_count"\s*:\s*(\d+)\s*,\s*"row_limit"',raw)
                    sql.append({'latency_ms':event.get('latency_ms'),'row_count':int(match[1]) if match else None,
                                'result_id':p.get('result_id'),'error':p.get('error')})
                if event['event']=='finding_read':
                    for f in p.get('findings',[]):
                        findings.append({'task_id':task,'source_task_id':f['source_task_id'],'memory_id':f['memory_id'],
                                         'similarity':f['similarity'],'source_log':log.name})
            calls=[e['payload'] for e in trace if e['event']=='model_call' and e['payload'].get('role')!='eval_judge']
            # Complete provider usage only; failed/missing usage is not zero.
            usage=[p.get('usage') for p in calls]
            total=sum(u['total_tokens'] for u in usage) if usage and all(u and isinstance(u.get('total_tokens'),int) for u in usage) else None
            row={'question_id':c['question_id'],'task_id':task,'source_log':log.name,'tag':s['tag'],
                 'steps':c.get('steps'),'tokens':total,'peak_context_tokens':c.get('peak_context_tokens'),
                 'termination':c.get('termination'),'sql_calls':sql,
                 'sql_total_ms':sum(q['latency_ms'] for q in sql) if all(q['latency_ms'] is not None for q in sql) else None,
                 'max_result_rows':max((q['row_count'] for q in sql if q['row_count'] is not None),default=None)}
            cases.append(row)
            if s['tag'].startswith('findings-dev-first'):finding_tasks.append(task)
    for f in findings:
        a,b=task_questions.get(f['task_id']),task_questions.get(f['source_task_id'])
        f['relation']='same_question' if a and a==b else 'different_question' if a and b else 'unknown'
    return sources,cases,findings,finding_tasks


def stats(cases):
    queries=[q for c in cases for q in c['sql_calls']]
    return {**{key:distribution([c[key] for c in cases]) for key in ('steps','tokens','peak_context_tokens','sql_total_ms','max_result_rows')},
            'sql_call_latency_ms':distribution([q['latency_ms'] for q in queries]),
            'sql_result_rows':distribution([q['row_count'] for q in queries])}


def stored_vector_pairs(task_ids):
    # These embeddings were created by Step 7. No embedding inference here.
    import psycopg
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        conn.execute('SET TRANSACTION READ ONLY')
        rows=conn.execute("SELECT memory_id,source_task_id,value->>'question',embedding::text,embedding_model,embedding_revision FROM memories WHERE type='finding' AND source_task_id=ANY(%s::uuid[]) ORDER BY memory_id",(task_ids,)).fetchall()
    vectors=[(str(r[0]),str(r[1]),r[2],json.loads(r[3]),r[4],r[5]) for r in rows]
    pairs=[]
    for a,b in itertools.combinations(vectors,2):
        if a[4:]!=b[4:] or len(a[3])!=len(b[3]):raise ValueError('Mixed stored embedding identities')
        dot=sum(x*y for x,y in zip(a[3],b[3])); norm=math.sqrt(sum(x*x for x in a[3])*sum(y*y for y in b[3]))
        pairs.append({'left':a[0],'right':b[0],'relation':'same_question' if a[2]==b[2] else 'different_question','similarity':dot/norm})
    identities=[{'memory_id':r[0],'task_id':r[1],'question_sha256':hashlib.sha256(r[2].encode()).hexdigest(),
                 'vector_sha256':hashlib.sha256(json.dumps(r[3],separators=(',',':')).encode()).hexdigest(),
                 'model':r[4],'revision':r[5]} for r in vectors]
    return {'source':'existing Step 7 first-run finding vectors; read-only database snapshot',
            'interpretation':'finding-to-finding cosine, NOT query-to-finding retrieval; cross-user offline diagnostic only',
            'vectors':identities,'pairs':pairs,
            'distributions':{kind:distribution([p['similarity'] for p in pairs if p['relation']==kind]) for kind in ('same_question','different_question')}}


def execute():
    sources,cases,findings,task_ids=collect()
    final=[c for c in cases if c['tag']=='step9-dev-final' or c['tag'].startswith('step9-holdout-r')]
    vectors=stored_vector_pairs(task_ids)
    summary={'method':'nearest-rank quantiles: sorted[ceil(n*p)-1]; repeated attempts are separate samples; missing excluded, never zero-filled',
             'new_model_calls':0,'new_embedding_calls':0,'final_config':FINAL_CONFIG,'sources':sources,
             'historical_mixed_config':stats(cases),'final_config_cohort':stats(final),
             'by_question_final':{q:stats([c for c in final if c['question_id']==q]) for q in sorted({c['question_id'] for c in final})},
             'by_run':{s['configuration']['tag']:stats([c for c in cases if c['tag']==s['configuration']['tag']]) for s in sources},
             'cases':cases,'accepted_finding_matches':findings,
             'accepted_match_distributions':{kind:distribution([f['similarity'] for f in findings if f['relation']==kind]) for kind in ('same_question','different_question','unknown')},
             'stored_finding_similarity':vectors,
             'limitations':['SQL timing is tool round-trip including MCP/network/database/persistence, not database-only execution.',
                'Only accepted top-3 retrieval matches were historically logged. Missing below-threshold and different-question retrieval cannot be reconstructed.',
                'Stored finding-to-finding pairs are correlated observations, not an independent retrieval test and cannot validate the 0.78 threshold.',
                'Historical mixed cohort includes failed/interrupted runs and changed configurations; use final cohort for current sizing, not causal comparisons.']}
    logger,path=start_log('step10_parameters')
    record(logger,'offline_statistics',**summary)
    summary.update(source_log=path.name,source_log_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    receipt=write_evidence(path.stem+'.summary.json',summary)
    print('Evidence:',receipt.name)
    return receipt,summary


if __name__=='__main__':execute()
