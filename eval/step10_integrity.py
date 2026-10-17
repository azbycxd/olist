"""Check frozen release, Step 10 receipts and test totals without model calls."""
import hashlib
import json
import math
import subprocess
import sys
import xml.etree.ElementTree as ET

from config import ROOT
from scripts.common import start_log, record
from scripts.evidence import write_evidence


def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True,encoding='utf-8').splitlines()


def main():
    baseline='f5899a7f38d8524aeba0d0823e592e8c5595a5fc'
    protected=['agent','mcp_olist','kb','sql/migrations','config.py','contracts.py',
               'scripts/runtime.py','scripts/preferences.py','scripts/findings.py',
               'eval/questions.jsonl','eval/checker.py','eval/scoring.py','eval/dataset.py',
               'docs/RESULTS.md','docs/FINAL_RESULTS.md','docs/RESUME.md']
    assert not git('diff','--name-only',baseline,'--',*protected),'Frozen runtime or results changed'
    old=set(git('ls-tree','-r','--name-only',baseline,'--','evidence'))
    changed=set(git('diff','--name-only',baseline,'--','evidence'))
    assert not old & changed,'Existing evidence modified'
    receipts=[]
    for path in sorted((ROOT/'evidence').glob('*step10*.summary.json')):
        if 'integrity' in path.name:continue
        s=json.loads(path.read_text(encoding='utf-8-sig'))
        log=ROOT/'logs'/(s.get('source_log') or s.get('control_log'))
        assert hashlib.sha256(log.read_bytes()).hexdigest()==s['source_log_sha256'],path.name
        receipts.append({'receipt':path.name,'source_log':log.name,'source_log_sha256':s['source_log_sha256']})
    boundary=list((ROOT/'evidence').glob('eval_step10-boundary_*.summary.json'));assert len(boundary)==1
    run=json.loads(boundary[0].read_text(encoding='utf-8'))
    protocol=json.loads((ROOT/'evidence/step10_boundary_protocol.json').read_text(encoding='utf-8'))
    assert protocol['question_sha256']==run['questions_sha256']==hashlib.sha256((ROOT/'eval/boundary_cases.json').read_bytes()).hexdigest()
    assert len(run['cases'])==len({c['task_id'] for c in run['cases']})==10
    assert all(c.get('termination')=='final_answer' for c in run['cases'])
    assert run['before']==run['after']
    holdout=list((ROOT/'evidence').glob('eval_step9-holdout-r*.summary.json'));assert len(holdout)==3
    assert sum(len(json.loads(p.read_text(encoding='utf-8'))['cases']) for p in holdout)==66
    params=json.loads(next((ROOT/'evidence').glob('step10_parameters_*.summary.json')).read_text(encoding='utf-8'))
    assert params['new_model_calls']==params['new_embedding_calls']==0
    cohort=[c for c in params['cases'] if c['tag']=='step9-dev-final' or c['tag'].startswith('step9-holdout-r')]
    for key in ('steps','tokens','peak_context_tokens','sql_total_ms','max_result_rows'):
        values=sorted(c[key] for c in cohort if c[key] is not None);d=params['final_config_cohort'][key]
        assert (d['n'],d['p50'],d['p95'],d['max'])==(len(values),values[math.ceil(len(values)*.5)-1],values[math.ceil(len(values)*.95)-1],values[-1])
    tests={}
    for name in ('step10_queue_tests.xml','step10_full_tests.xml','step10_mcp_tests.xml'):
        suite=ET.parse(ROOT/'evidence'/name).getroot().find('testsuite')
        tests[name]={k:int(suite.get(k,0)) for k in ('tests','failures','errors','skipped')}
        assert tests[name]['failures']==tests[name]['errors']==0
    assert tests['step10_full_tests.xml']['tests']-tests['step10_full_tests.xml']['skipped']==184
    assert tests['step10_mcp_tests.xml']['tests']==1 and not tests['step10_mcp_tests.xml']['skipped']
    checks={'frozen_runtime_and_results_unchanged':True,'old_evidence_unchanged':True,'holdout_runs_unchanged':True,
            'one_boundary_run':True,'boundary_protocol_hash_matches':True,'business_rows_unchanged':True,
            'parameter_quantiles_recomputed':True,'new_model_calls_for_parameter_analysis':0}
    logger,log=start_log('step10_integrity')
    summary={'baseline_commit':baseline,'checks':checks,'protected_paths':protected,'receipts':receipts,'tests':tests,
             'changed_production_behavior':['task_worker: three issued leases maximum; fourth pickup fails and records reason',
                 'task_worker: worker identity and claim count in event metadata'],
             'scope':'Holdout used adapter/runtime, not background task_worker; historical scores unchanged, not remeasured.',
             'source_log':log.name}
    record(logger,'integrity',**summary)
    summary['source_log_sha256']=hashlib.sha256(log.read_bytes()).hexdigest()
    print('Evidence:',write_evidence(log.stem+'.summary.json',summary).name)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
