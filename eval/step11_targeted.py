"""One user-authorized targeted repair: two D passes and two boundary passes."""
import hashlib
import json
import os
import zipfile
from argparse import Namespace

from config import ROOT,FINAL_CONFIG
from eval.final_suite import BASE,source_hashes
from eval.boundary import execute as boundary
from scripts.common import start_log,record
from scripts.evidence import write_evidence

MARKER='step11_targeted_protocol.json'


def acceptance(d_counts,boundary_counts):
    return (len(d_counts)==2 and all(total==8 and correct>=6 for correct,total in d_counts)
            and len(boundary_counts)==2 and all(total==10 and correct>=8 for correct,total in boundary_counts))


def frozen_files():
    # This includes prior holdout receipts/protocol/archive and the original
    # question file and migrations. Never execute or rescore holdout here.
    ref=json.loads((ROOT/'evidence/step11_frozen_reference.json').read_text(encoding='utf-8'))
    for name,digest in ref['immutable_files'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:
            raise RuntimeError('Frozen historical file changed: '+name)
    return ref


def execute_suite(execute):
    marker=ROOT/'evidence'/MARKER
    if marker.exists():raise ValueError('Targeted protocol already started; no further model attempts authorized')
    config={**FINAL_CONFIG,'BOUNDARY_GUARDS':'true'}
    os.environ.update(config)
    from mcp_olist.boundaries import data_context
    if not data_context()['dimension_precheck']:raise RuntimeError('Dimension precheck must remain enabled')
    hashes=source_hashes()
    logger,path=start_log('eval_step11-targeted-protocol')
    protocol={'source_log':path.name,'source_sha256':hashes,'configuration':config,
        'judge':'same eval/checker.py and scoring.py for all D passes; unchanged from Step 11',
        'checker_sha256':hashes['eval/checker.py'],'scoring_sha256':hashes['eval/scoring.py'],
        'runs':['step11-target-d-r1','step11-target-d-r2','step11-target-original','step11-target-new'],
        'criteria':{'D':'both passes >=6/8','boundaries':'both groups >=8/10'},
        'boundary_rubric':'Unchanged expected text in both case files; inspect saved responses against expected behavior. Business numbers must be direct SQL results; metadata and harmless formatting mismatches recorded separately. No extra judge model; Codex review is not blinded.',
        'selection':'Adopt BOUNDARY_GUARDS=true only if all thresholds pass; otherwise false restores Step 9 prompts/number gate. DIMENSION_PRECHECK remains true and engineering task controls remain.',
        'stop':'Exactly these four complete passes; no selective retries, further tuning or fallback model runs; never holdout',
        'source_archive':'step11_targeted_source.zip','frozen_reference':frozen_files()}
    with marker.open('x',encoding='utf-8') as f:json.dump(protocol,f,ensure_ascii=False,indent=2)
    with zipfile.ZipFile(ROOT/'evidence'/protocol['source_archive'],'x',zipfile.ZIP_DEFLATED) as z:
        for name in hashes:z.write(ROOT/name,name)
    record(logger,'protocol_started',**protocol)
    receipts={}
    for name in protocol['runs']:
        if source_hashes()!=hashes:raise RuntimeError('Code changed after freeze')
        print('Starting:',name,flush=True)
        if name.startswith('step11-target-d-'):
            result=execute(Namespace(**BASE,split='dev',categories=['D'],tag=name))
        else:
            suite='step11-original' if name.endswith('original') else 'step11-new'
            result=boundary(suite,tag=name,runtime_config=config)
        receipts[name]=result['source_log'].replace('.jsonl','.summary.json')
        record(logger,'pass_completed',name=name,evidence=receipts[name])
    if source_hashes()!=hashes:raise RuntimeError('Code changed during protocol')
    frozen_files()
    summary={**protocol,'receipts':receipts,'complete':True,'behavior_review':'pending saved-response review'}
    record(logger,'run_summary',**summary)
    summary['source_log_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    print('Evidence:',write_evidence(path.stem+'.summary.json',summary).name,flush=True)
