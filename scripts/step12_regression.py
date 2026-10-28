"""One committed-protocol C/D/E dev run. Never retries, rechecks or scores holdout."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
from datetime import datetime,timezone
from types import SimpleNamespace
from decimal import Decimal,InvalidOperation


PRICE_KEYS=('TOKEN_PRICE_INPUT','TOKEN_PRICE_CACHED_INPUT','TOKEN_PRICE_OUTPUT')


def require_prices():
    prices={}
    for key in PRICE_KEYS:
        try:
            value=Decimal(os.environ.get(key,''))
            if not value.is_finite() or value<0:raise ValueError()
            prices[key]=float(value)
            if prices[key]==float('inf'):raise ValueError()
        except (InvalidOperation,ValueError):
            raise ValueError(f'Configure {key} in .env before starting v2') from None
    return prices


def version_paths(root,version):
    suffix='' if version==1 else '_v2'
    return tuple(root/'evidence'/f'step12_regression_{name}{suffix}.json' for name in ('protocol','started','results'))


def verify_rehearsal(protocol,root):
    proof=protocol['rehearsal']
    path=root/proof['path']
    if hashlib.sha256(path.read_bytes()).hexdigest()!=proof['sha256']:
        raise ValueError('Rehearsal evidence hash mismatch')
    report=json.loads(path.read_text(encoding='utf-8'))
    if report['completed']!=31 or report['engineering_errors'] or report['real_model_calls']!=0:
        raise ValueError('A complete successful model-double rehearsal is required')
    if len(report['sql_execution_events'])!=31 or any(n<2 for n in report['sql_execution_events'].values()):
        raise ValueError('Rehearsal did not exercise parallel SQL event writers')
    if any(key in protocol['config'] for key in PRICE_KEYS):
        raise ValueError('v2 prices must come from .env, not protocol config overrides')


def claim_once(protocol_path,marker):
    protocol=json.loads(protocol_path.read_text(encoding='utf-8'))
    if (protocol.get('split')!='dev' or protocol.get('categories')!=['C','D','E'] or
        protocol.get('runs')!=1 or protocol.get('holdout') is not False or
        not protocol.get('independent_user_per_question') or not protocol.get('no_rerun') or not protocol.get('no_tuning')):
        raise ValueError('Regression must be one dev-only run, independent users, no reruns or tuning')
    with marker.open('x',encoding='utf-8') as out:
        json.dump({'started_at':datetime.now(timezone.utc).isoformat(),'protocol_sha256':hashlib.sha256(protocol_path.read_bytes()).hexdigest()},out,indent=2)
    return protocol


def verify_committed_protocol(path,root):
    digest=hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
    relative=path.relative_to(root).as_posix()
    if shutil.which('git'):
        committed=subprocess.check_output(['git','-c',f'safe.directory={root}','show','HEAD:'+relative],cwd=root)
        if hashlib.sha256(committed.replace(b'\r\n',b'\n')).hexdigest()!=digest:raise ValueError('Commit the exact protocol before evaluation')
        return subprocess.check_output(['git','-c',f'safe.directory={root}','log','-1','--format=%H','--',relative],cwd=root,text=True).strip()
    # The host verifies git show and supplies a matching committed-blob digest.
    commit=os.getenv('STEP12_PROTOCOL_COMMIT','')
    if len(commit)!=40 or any(c not in '0123456789abcdef' for c in commit) or os.getenv('STEP12_PROTOCOL_SHA256')!=digest:
        raise ValueError('Missing/mismatched host-verified committed protocol ticket')
    return commit


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--version',type=int,choices=[1,2],default=1)
    version=parser.parse_args().version
    root=Path(__file__).resolve().parents[1]
    path,marker,result_path=version_paths(root,version)
    protocol=json.loads(path.read_text(encoding='utf-8'))
    protocol_commit=verify_committed_protocol(path,root)
    prices=None
    if version==2:
        verify_rehearsal(protocol,root)
        prices=require_prices()  # Before imports, MCP startup, marker, or any model request.
    if marker.exists():raise FileExistsError('This regression has already started; do not rerun')
    for key,value in protocol['config'].items():os.environ[key]=str(value)
    from config import db_kwargs
    from eval.dataset import load_questions,QUESTION_FILE
    selected=[q for q in load_questions() if q['split']=='dev' and q['category'] in 'CDE']
    if [q['id'] for q in selected]!=protocol['question_ids'] or hashlib.sha256(QUESTION_FILE.read_bytes()).hexdigest()!=protocol['question_file_sha256']:
        raise ValueError('Question workload differs from the committed protocol')
    from eval.robustness import start_private_mcp
    from eval.run import execute
    process,url=start_private_mcp();os.environ['MCP_URL']=url
    try:
        claim_once(path,marker)
        args=SimpleNamespace(adapter='single',judge='off',categories=['C','D','E'],split='dev',
            tag='step12-regression-once' if version==1 else 'step12-regression-v2-once',schema_mode='on_demand',context_strategy='none',
            context_limit=16000,context_summary_threshold=6000,rag_mode='inject',use_memory='true',
            agent_mode='single',number_gate='true',token_budget=100000,question_ids=None,user_group=None)
        summary=execute(args)
    finally:
        process.terminate()
        try:process.wait(timeout=30)
        except subprocess.TimeoutExpired:process.kill();process.wait()
    # Usage is read from persisted model events including E preference setup.
    # No model, oracle or checker is invoked by this receipt-building section.
    import psycopg
    from telemetry import usage_summary
    cases=[]
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        for case in summary['cases']:
            usages=conn.execute("SELECT payload->'usage' FROM events WHERE task_id=%s AND type='model_call' ORDER BY seq",(case['task_id'],)).fetchall()
            values=[usage_summary(row[0]) for row in usages]
            def total(key):return sum(v[key] for v in values) if values and all(v[key] is not None for v in values) else None
            incoming,cached=total('input_tokens'),total('cached_tokens')
            cases.append({'id':case['question_id'],'category':case['category'],'correct':case['correct'],
                'task_id':case['task_id'],'user_id':case['user_id'],'tokens':case['agent_usage']['total_tokens'],
                'elapsed_ms':case['latency_ms'],'input_tokens':incoming,'cached_tokens':cached,'output_tokens':total('output_tokens'),
                'cache_hit_ratio':cached/incoming if cached is not None and incoming else None,'cost_yuan':total('cost_yuan'),
                'termination':case.get('termination'),'error':case.get('error')})
    counts={c:sum(r['correct'] for r in cases if r['category']==c) for c in 'CDE'}
    costs=[r['cost_yuan'] for r in cases];known_prices=all(c is not None for c in costs)
    input_total=sum(r['input_tokens'] or 0 for r in cases);cached_total=sum(r['cached_tokens'] or 0 for r in cases)
    report={'model_kind':'真实模型；C/D/E dev一次性默认配置回归','version':version,'protocol_commit':protocol_commit,
        'protocol_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'cases':cases,'correct':counts,
        'passed':all(counts[c]>=protocol['pass'][c] for c in 'CDE'),'total_tokens':sum(r['tokens'] or 0 for r in cases),
        'average_cost_yuan':sum(costs)/len(costs) if known_prices else None,
        'total_cost_yuan':sum(costs) if known_prices else None,'pricing_yuan_per_million':prices,
        'cache_hit_ratio':cached_total/input_total if input_total and all(r['cached_tokens'] is not None for r in cases) else None,
        'pricing_note':'v2必须配置三种单价；若供应商未返回缓存用量则费用未知，不估算','source_log':summary['source_log'],'source_log_sha256':summary['source_log_sha256'],
        'source_receipt':'evidence/'+summary['source_log'].replace('.jsonl','.summary.json'),'reruns':0,'holdout_runs':0}
    result_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('correct','passed','total_tokens','average_cost_yuan','cache_hit_ratio')},ensure_ascii=False))


if __name__=='__main__':main()
