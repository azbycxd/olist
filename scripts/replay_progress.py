"""Read existing final-cohort logs only. No model, database, or scoring imports."""
import hashlib
import json
from collections import defaultdict
from datetime import datetime,timezone
from uuid import uuid4

from agent.progress import Progress
from config import ROOT
from scripts.evidence import write_evidence


def replay(trace):
    guard = Progress()
    pending, observations, steps = False, [], 0
    incomplete = 0
    for event in trace:
        p=event.get('payload',{})
        if event['event']=='model_call' and p.get('role')=='agent' and p.get('output_summary'):
            if pending:
                rule=guard.after(observations)
                if rule: return {'rule':rule,'step':steps,'incomplete_results':incomplete}
            steps+=1
            calls=p['output_summary'].get('tool_calls') or []
            rule=guard.before([(c['function']['name'],c['function']['arguments']) for c in calls])
            if rule: return {'rule':rule,'step':steps,'incomplete_results':incomplete}
            if any(c['function']['name']=='final_answer' for c in calls):
                return {'rule':None,'step':steps,'incomplete_results':incomplete}
            pending=True; observations=[]
        elif pending and event['event']=='tool_result' and p.get('phase')=='agent':
            try: content=json.loads(p['output_summary'])
            except (KeyError,ValueError,TypeError):
                incomplete+=1
                content={}
            observations.append({**content,'result_id':p.get('result_id') or content.get('result_id'),
                'error':p.get('error') or content.get('error')})
    rule=guard.after(observations) if pending else None
    return {'rule':rule,'step':steps,'incomplete_results':incomplete}


def main():
    tags={'step9-dev-final','step9-holdout-r1','step9-holdout-r2','step9-holdout-r3'}
    sources=[]; runs=[]; seen=set()
    for path in sorted((ROOT/'evidence').glob('eval_*.summary.json')):
        summary=json.loads(path.read_text(encoding='utf-8'))
        if summary.get('tag') not in tags or summary.get('recheck_only'): continue
        source=ROOT/'logs'/summary['source_log']
        digest=hashlib.sha256(source.read_bytes()).hexdigest()
        if digest!=summary['source_log_sha256']: raise ValueError('Historical log hash mismatch: '+source.name)
        by_task=defaultdict(list)
        for line in source.read_text(encoding='utf-8').splitlines():
            event=json.loads(line)
            if event.get('task_id'): by_task[event['task_id']].append(event)
        sources.append({'receipt':path.name,'source_log':source.name,'source_log_sha256':digest,'tag':summary['tag']})
        for case in summary['cases']:
            task=case['task_id']
            if task in seen: continue
            seen.add(task)
            if not by_task[task]: raise ValueError('Missing task trace: '+task)
            runs.append({'task_id':task,'source_log':source.name,**replay(by_task[task])})
    if len(sources)!=4 or len(runs)!=97: raise ValueError('Final cohort incomplete; expected four sources and 97 runs')
    payload={'new_model_calls':0,'new_embedding_calls':0,'rescoring':False,'sources':sources,
        'run_count':len(runs),'false_positives':sum(r['rule'] is not None for r in runs),
        'incomplete_results':sum(r['incomplete_results'] for r in runs),'runs':runs,
        'limitation':'Truncated historical result JSON is treated as unknown, not empty; result_id/error metadata remain usable. This is guard replay, not holdout scoring.'}
    stem='step12_a2_replay_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid4().hex[:8]
    log=ROOT/'evidence'/(stem+'.jsonl')
    log.write_text(json.dumps(payload,ensure_ascii=False)+'\n',encoding='utf-8')
    receipt=write_evidence(stem+'.summary.json',{**payload,'source_log':log.name,'source_log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()})
    print(json.dumps({'receipt':receipt.name,'run_count':len(runs),'false_positives':payload['false_positives'],'incomplete_results':payload['incomplete_results']}))
    if payload['false_positives']: raise AssertionError('Replay detected false positives; stop and report without tuning')


if __name__=='__main__': main()
