"""One slot experiment: rehearse both real entrances, then a committed one-shot run.

This wrapper never changes gold, scoring, SQL guards or evaluator behavior.
Boundary review consumes saved answers only; finalize never calls a model/DB.
"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import threading
from types import SimpleNamespace
from uuid import uuid4

from scripts.step12_regression import require_prices, verify_committed_protocol
from scripts.step12_rehearsal import response_message

COUNTS = {'C':17, 'D':8, 'E':6}
THRESHOLDS = {'C':17, 'D':6, 'E':6, 'boundary':8}
BOUNDARY_IDS = [f'X{i:02}' for i in range(1,11)]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, payload, *, exclusive=False):
    with Path(path).open('x' if exclusive else 'w', encoding='utf-8', newline='\n') as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def slot_configuration(root):
    return {**read(root/'evidence/step12_regression_protocol_v2.json')['config'], 'SLOT_RESOLUTION':'true'}


def validate_plan(protocol, root):
    fixed = {'split':'dev','categories':['C','D','E'],'runs':1,'holdout':False,
        'independent_user_per_question':True,'no_rerun':True,'no_tuning':True,
        'pass':THRESHOLDS,'boundary_suite':'step11-original','boundary_runs':1,
        'config':slot_configuration(root),
        'invalidation':{'reproducible_engineering_failure':True,'failing_test_committed_first':True,'wrong_answers_do_not_invalidate':True}}
    if any(protocol.get(k)!=v for k,v in fixed.items()):
        raise ValueError('Slot protocol must keep the fixed workload, configuration, thresholds and invalidation rules')


def workload(root):
    dev=[q['id'] for q in (json.loads(line) for line in (root/'eval/questions.jsonl').read_text(encoding='utf-8').splitlines())
         if q['split']=='dev' and q['category'] in COUNTS]
    boundary=[q['id'] for q in read(root/'eval/boundary_cases.json')]
    if len(dev)!=31 or len(set(dev))!=31 or boundary!=BOUNDARY_IDS:
        raise ValueError('Expected the frozen 31 dev and original 10 boundary cases')
    return dev,boundary


def code_snapshot(root):
    paths=[root/p for p in ('config.py','contracts.py','db_pool.py','telemetry.py','privacy.py','pyproject.toml','Dockerfile','docker-compose.yml','.env.example')]
    for directory in ('agent','api','mcp_olist','scripts','eval'):
        paths.extend(sorted((root/directory).glob('*.py')))
    paths.extend(sorted((root/'kb').glob('*.md')))
    paths.extend(sorted((root/'sql/migrations').glob('*.sql')))
    # Canonical LF hashes match the built Linux image as well as a Windows checkout.
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest() for p in paths}


def validate_rehearsal(report, dev_ids, boundary_ids):
    if report.get('real_model_calls')!=0 or '替身演练' not in report.get('kind',''):
        raise ValueError('An explicitly labelled model-double rehearsal is required')
    dev,boundary=report.get('dev',[]),report.get('boundary',[])
    if [r['id'] for r in dev]!=dev_ids or [r['id'] for r in boundary]!=boundary_ids:
        raise ValueError('Both complete evaluator entrances are required')
    cases=dev+boundary
    if len({r['user_id'] for r in cases})!=41 or len({r['task_id'] for r in cases})!=41:
        raise ValueError('Rehearsal cases must use independent users/tasks')
    for row in cases:
        if row.get('error') or row.get('termination')!='final_answer' or row.get('slot_events')!=1:
            raise ValueError('Rehearsal has engineering failures or did not activate slots')
        if row.get('clarification'):
            if row['model_calls']!=0 or row['sql_events']!=0:
                raise ValueError('Missing-time clarification must precede every model/SQL call')
        elif row.get('sql_events',0)<2 or row.get('model_calls',0)<1:
            raise ValueError('Non-clarification rehearsal cases must exercise parallel SQL/event persistence')


def verify_workload_and_proof(protocol, root):
    dev,boundary=workload(root)
    for key,actual in (('question_ids',dev),('boundary_ids',boundary),
                       ('question_file_sha256',digest(root/'eval/questions.jsonl')),
                       ('boundary_file_sha256',digest(root/'eval/boundary_cases.json')),
                       ('source_hashes',code_snapshot(root))):
        if protocol.get(key)!=actual: raise ValueError(f'Frozen slot workload/source differs: {key}')
    proof=protocol['rehearsal'];path=root/proof['path']
    if digest(path)!=proof['sha256']: raise ValueError('Slot rehearsal hash differs')
    rehearsal=read(path)
    validate_rehearsal(rehearsal,dev,boundary)
    if rehearsal['source_hashes']!=protocol['source_hashes']:
        raise ValueError('Rehearsal used different product code')


def claim_marker(path, commit, protocol_hash, kind):
    write(path,{'kind':kind,'started_at':datetime.now(timezone.utc).isoformat(),
                'protocol_commit':commit,'protocol_sha256':protocol_hash},exclusive=True)


def case_cost(usages, prices):
    from telemetry import usage_summary
    values=[usage_summary(u) for u in usages]
    def total(key):
        return sum(v[key] for v in values) if all(v[key] is not None for v in values) else None
    incoming,cached,outgoing=total('input_tokens'),total('cached_tokens'),total('output_tokens')
    cost=None
    if all(v is not None for v in (incoming,cached,outgoing)):
        cost=(Decimal(incoming-cached)*Decimal(str(prices['TOKEN_PRICE_INPUT']))+
              Decimal(cached)*Decimal(str(prices['TOKEN_PRICE_CACHED_INPUT']))+
              Decimal(outgoing)*Decimal(str(prices['TOKEN_PRICE_OUTPUT'])))/1000000
    return {'model_calls':len(values),'input_tokens':incoming,'cached_tokens':cached,'output_tokens':outgoing,
        'tokens':incoming+outgoing if incoming is not None and outgoing is not None else None,
        'cost_yuan':float(cost) if cost is not None else None,'cost_yuan_decimal':str(cost) if cost is not None else None,
        'cache_hit_ratio':cached/incoming if cached is not None and incoming else None}


def collect_rows(summary, *, boundary, prices):
    import psycopg
    from config import db_kwargs
    cases=[]
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        for c in summary['cases']:
            tid=c['task_id']
            events=conn.execute('SELECT type,payload FROM events WHERE task_id=%s ORDER BY seq',(tid,)).fetchall()
            slots=[payload for kind,payload in events if kind=='slot_resolution']
            usages=[payload.get('usage') for kind,payload in events if kind=='model_call']
            owner=str(conn.execute('SELECT user_id FROM tasks WHERE task_id=%s',(tid,)).fetchone()[0])
            cases.append({'id':c['id'] if boundary else c['question_id'],'category':'boundary' if boundary else c['category'],
                'correct':None if boundary else c['correct'],'task_id':tid,'user_id':owner,
                'termination':c.get('termination'),'error':c.get('error'),'elapsed_ms':c['latency_ms'],
                'slot_events':len(slots),'slots':slots,'clarification':bool(slots and slots[0].get('clarification')),
                'sql_events':sum(kind=='sql_execution' for kind,_ in events),**case_cost(usages,prices)})
    return cases


def decide(dev, review):
    if len(dev)!=31 or len({r['id'] for r in dev})!=31 or {c:sum(r['category']==c for r in dev) for c in COUNTS}!=COUNTS:
        raise ValueError('Adoption requires all 31 dev cases')
    if sorted(r['id'] for r in review)!=BOUNDARY_IDS or any(type(r.get('passed')) is not bool for r in review):
        raise ValueError('Adoption requires one explicit review for each of the 10 boundary cases')
    counts={c:sum(r['correct'] is True for r in dev if r['category']==c) for c in COUNTS}
    counts['boundary']=sum(r['passed'] for r in review)
    return {'correct':counts,'pass':dict(THRESHOLDS),'adopt':all(counts[c]>=THRESHOLDS[c] for c in THRESHOLDS)}


def compare_v2(previous, current):
    old={r['id']:r for r in previous};new={r['id']:r for r in current}
    if set(old)!=set(new) or len(old)!=len(previous) or len(new)!=len(current):
        raise ValueError('Comparison must keep exactly the same dev cases')
    cases=[]
    for key,a in old.items():
        b=new[key]
        def delta(field):
            return float(Decimal(str(b[field]))-Decimal(str(a[field]))) if a[field] is not None and b[field] is not None else None
        cases.append({'id':key,'v2_correct':a['correct'],'slot_correct':b['correct'],
            'v2_tokens':a['tokens'],'slot_tokens':b['tokens'],'token_delta':delta('tokens'),
            'v2_cost_yuan':a['cost_yuan'],'slot_cost_yuan':b['cost_yuan'],'cost_delta_yuan':delta('cost_yuan')})
    return {'pass_to_fail':[r['id'] for r in cases if r['v2_correct'] and not r['slot_correct']],
            'fail_to_pass':[r['id'] for r in cases if not r['v2_correct'] and r['slot_correct']], 'cases':cases}


def run_entrances(tag):
    from eval.robustness import start_private_mcp
    from eval.run import execute
    from eval.boundary import execute as boundary_execute
    from config import ROOT
    process,url=start_private_mcp();os.environ['MCP_URL']=url
    try:
        dev=execute(SimpleNamespace(adapter='single',judge='off',categories=['C','D','E'],split='dev',tag=tag,
            schema_mode='on_demand',context_strategy='none',context_limit=16000,context_summary_threshold=6000,
            rag_mode='inject',use_memory='true',agent_mode='single',number_gate='true',token_budget=100000,
            question_ids=None,user_group=None))
        boundary=boundary_execute('step11-original',tag=tag,runtime_config=slot_configuration(ROOT))
        return dev,boundary
    finally:
        process.terminate()
        try: process.wait(timeout=30)
        except subprocess.TimeoutExpired: process.kill();process.wait()


def source_receipts(root, summaries):
    return [{'path':'evidence/'+s['source_log'].replace('.jsonl','.summary.json'),
             'sha256':digest(root/'evidence'/s['source_log'].replace('.jsonl','.summary.json')),
             'log':'logs/'+s['source_log'],'log_sha256':s['source_log_sha256']} for s in summaries]


def rehearse(root, attempt):
    suffix='' if attempt==1 else f'_attempt{attempt}'
    kind='模型替身；替身演练，不是成绩'
    claim_marker(root/f'evidence/step12_slot_rehearsal{suffix}_started.json',None,None,kind)
    for key in ('DEEPSEEK_MODEL','DEEPSEEK_BASE_URL','DEEPSEEK_API_KEY'): os.environ.pop(key,None)
    os.environ['OLIST_LOAD_DOTENV']='0'
    calls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            message=response_message(body)
            calls.append({'json_mode':bool(body.get('response_format'))})
            data=json.dumps({'id':'slot-double-'+uuid4().hex,'object':'chat.completion','created':0,'model':'slot-http-double',
                'choices':[{'index':0,'finish_reason':'tool_calls' if 'tool_calls' in message else 'stop','message':message}],
                'usage':{'prompt_tokens':900,'prompt_cache_hit_tokens':0,'completion_tokens':100,'total_tokens':1000}}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)))
            self.end_headers();self.wfile.write(data)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    os.environ.update(OPENAI_BASE_URL=f'http://127.0.0.1:{server.server_port}/v1',OPENAI_MODEL='slot-http-double',OPENAI_API_KEY='fixture-not-a-secret')
    try:
        dev,boundary=run_entrances('step12-slot-rehearsal-model-double-not-score'+suffix)
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)
    prices={k:0 for k in ('TOKEN_PRICE_INPUT','TOKEN_PRICE_CACHED_INPUT','TOKEN_PRICE_OUTPUT')}
    report={'kind':kind,'real_model_calls':0,'http_model_double_calls':len(calls),'config':slot_configuration(root),
        'dev':collect_rows(dev,boundary=False,prices=prices),'boundary':collect_rows(boundary,boundary=True,prices=prices),
        'sources':source_receipts(root,(dev,boundary)),'source_hashes':code_snapshot(root),
        'cost_note':'Synthetic token usage; no real model quality, throughput or cost claim'}
    write(root/f'evidence/step12_slot_rehearsal{suffix}.json',report,exclusive=True)
    validate_rehearsal(report,*workload(root))
    print(json.dumps({'kind':kind,'dev_completed':len(report['dev']),'boundary_completed':len(report['boundary']),
                      'engineering_errors':0,'http_model_double_calls':len(calls)},ensure_ascii=False))


def run_once(root):
    path=root/'evidence/step12_slot_protocol.json';protocol=read(path)
    validate_plan(protocol,root)
    commit=verify_committed_protocol(path,root)
    verify_workload_and_proof(protocol,root)
    prices=require_prices()
    claim_marker(root/'evidence/step12_slot_started.json',commit,digest(path),'真实模型；槽位一次性评估')
    try:
        dev,boundary=run_entrances('step12-slot-once')
        report={'kind':'真实模型；槽位一次性评估，边界评分等待保存回答复核','protocol_commit':commit,
            'protocol_sha256':digest(path),'pricing_yuan_per_million':prices,'config':protocol['config'],
            'dev':collect_rows(dev,boundary=False,prices=prices),'boundary':collect_rows(boundary,boundary=True,prices=prices),
            'sources':source_receipts(root,(dev,boundary)),'source_hashes':code_snapshot(root),'reruns':0,'holdout_runs':0}
        write(root/'evidence/step12_slot_observations.json',report,exclusive=True)
        print(json.dumps({'dev_completed':len(report['dev']),'boundary_completed':len(report['boundary']),
                          'correct':{c:sum(r['correct'] for r in report['dev'] if r['category']==c) for c in COUNTS}},ensure_ascii=False))
    except Exception as exc:
        write(root/'evidence/step12_slot_run_error.json',{'error_type':type(exc).__name__,'rerun_permitted':False,
            'instruction':'Keep all raw receipts; diagnose and commit a reproducing failed test before proposing invalidation.'},exclusive=True)
        raise


def finalize(root):
    observation_path=root/'evidence/step12_slot_observations.json';observed=read(observation_path)
    review_path=root/'evidence/step12_slot_boundary_review.json';review=read(review_path)
    boundary_source=observed['sources'][1]
    if review['source_sha256']!=boundary_source['sha256'] or digest(root/boundary_source['path'])!=review['source_sha256']:
        raise ValueError('Boundary review must identify the exact saved run')
    plan=read(root/'evidence/step12_slot_protocol.json');validate_plan(plan,root)
    if digest(root/'evidence/step12_slot_protocol.json')!=observed['protocol_sha256']:raise ValueError('Protocol changed after running')
    old_path=root/'evidence/step12_regression_results_v2.json'
    if digest(old_path)!=plan['v2_baseline']['sha256']:raise ValueError('Frozen v2 baseline changed')
    report={**observed,'kind':'真实模型；已完成固定协议判定',**decide(observed['dev'],review['cases']),
        'boundary_review':{'path':str(review_path.relative_to(root)),'sha256':digest(review_path)},
        'observations_sha256':digest(observation_path),'comparison':compare_v2(read(old_path)['cases'],observed['dev'])}
    write(root/'evidence/step12_slot_results.json',report,exclusive=True)
    print(json.dumps({k:report[k] for k in ('correct','pass','adopt')},ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['rehearse','run','finalize'])
    parser.add_argument('--attempt',type=int,default=1);args=parser.parse_args()
    # Load local credentials once. Configuration is frozen before evaluator imports.
    from config import ROOT
    if args.action=='finalize':return finalize(ROOT)
    os.environ.update(slot_configuration(ROOT))
    if args.action=='rehearse':rehearse(ROOT,args.attempt)
    else:run_once(ROOT)


if __name__=='__main__':main()
