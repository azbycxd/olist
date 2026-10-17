"""One fixed Step 11 protocol; no holdout execution or selective retries."""
import hashlib
import json
import os
from argparse import Namespace
from config import ROOT
from eval.final_suite import BASE,source_hashes
from eval.boundary import execute as boundary
from scripts.common import start_log,record
from scripts.evidence import write_evidence

BASELINE='eval_step9-dev-final_20261017T102853Z_45a71d7d.summary.json'


def execute_suite(execute,recheck):
    marker=ROOT/'evidence/step11_protocol.json'
    if marker.exists():raise ValueError('Step 11 protocol already started; retain all attempts, no selective retries')
    hashes=source_hashes()
    logger,path=start_log('eval_step11-protocol')
    protocol={'source_log':path.name,'source_sha256':hashes,'repetitions':1,
              'runs':['step11-original','step11-new','step11-dev-final'],
              'baseline':BASELINE,'holdout':'frozen, pre-Step11 runtime; no rerun or rescoring',
              'boundary_grading':'predeclared expectations and saved-response inspection; not a blinded human review',
              'dev_config':{**BASE,'split':'dev','categories':list('CDE')}}
    with marker.open('x',encoding='utf-8') as f:json.dump(protocol,f,ensure_ascii=False,indent=2)
    record(logger,'protocol_started',**protocol)
    os.environ['RETRIEVAL_METHOD']='vector'
    recheck(ROOT/'evidence'/BASELINE,'step11-baseline-recheck')
    runs={}
    for name in protocol['runs']:
        if source_hashes()!=hashes:raise RuntimeError('Source changed during fixed Step 11 protocol')
        print('Starting:',name,flush=True)
        result=execute(Namespace(**BASE,split='dev',categories=list('CDE'),tag=name)) if name=='step11-dev-final' else boundary(name)
        runs[name]=result['source_log'].replace('.jsonl','.summary.json')
        record(logger,'pass_completed',name=name,evidence=runs[name])
    if source_hashes()!=hashes:raise RuntimeError('Source changed during protocol')
    summary={**protocol,'receipts':runs,'complete':True}
    record(logger,'run_summary',**summary)
    summary['source_log_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    receipt=write_evidence(path.stem+'.summary.json',summary)
    print('Evidence:',receipt.name,flush=True)


def repair_dev(execute,recheck):
    """Keep the failing pass; freeze one corrective pass, never selective retries."""
    prior=list((ROOT/'evidence').glob('eval_step11-dev-final_*.summary.json'))
    if len(prior)!=1:raise ValueError('Exactly one initial Step 11 dev receipt required')
    marker=ROOT/'evidence/step11_repair_dev_protocol.json'
    hashes=source_hashes()
    logger,path=start_log('eval_step11-repair-protocol')
    protocol={'source_log':path.name,'source_sha256':hashes,'repetitions':1,
        'retained_initial_run':prior[0].name,'baseline':BASELINE,
        'reason':'Initial dev regressed: dataset metadata put into unsupported claims; numeric definition/conversion constants absent from SQL output. Clarify the contract; repair date/tool formats and unsafe time-assumption fallback.',
        'limits':'Only one corrective CDE pass; no additional boundaries or holdout; keep before/after results',
        'config':{**BASE,'split':'dev','categories':list('CDE')}}
    with marker.open('x',encoding='utf-8') as f:json.dump(protocol,f,ensure_ascii=False,indent=2)
    record(logger,'protocol_started',**protocol)
    os.environ['RETRIEVAL_METHOD']='vector'
    recheck(ROOT/'evidence'/BASELINE,'step11-baseline-final-checker')
    recheck(prior[0],'step11-initial-final-checker')
    result=execute(Namespace(**BASE,split='dev',categories=list('CDE'),tag='step11-dev-repair'))
    if source_hashes()!=hashes:raise RuntimeError('Source changed during correction protocol')
    summary={**protocol,'receipt':result['source_log'].replace('.jsonl','.summary.json'),'complete':True}
    record(logger,'run_summary',**summary)
    summary['source_log_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    print('Evidence:',write_evidence(path.stem+'.summary.json',summary).name,flush=True)
