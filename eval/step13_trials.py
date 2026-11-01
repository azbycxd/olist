"""Empirical three-trial analysis and registered run gates; no historical rescoring."""
import argparse
from collections import defaultdict
from datetime import datetime,timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from eval.step13_errors import ROOT,read,write,sha,load_source,RUNS


def workload(suite):
    if suite=='dev':
        from eval.dataset import load_questions
        return [q for q in load_questions() if q['split']=='dev']
    if suite in {'supplement','paired','regression','capability'}:return read(ROOT/f'eval/step13_{suite}_cases.json')
    raise ValueError('Unknown suite')


def summarize_trials(rows):
    grouped=defaultdict(list)
    for r in rows:grouped[r['id']].append(r)
    questions=[]
    for qid,items in grouped.items():
        if len(items)!=3 or {r['repeat'] for r in items}!={1,2,3}:raise ValueError('Exactly three unique trials per question required')
        items.sort(key=lambda r:r['repeat']);values=[r['correct'] for r in items]
        if any(v is not None and type(v) is not bool for v in values):raise ValueError('Judgments must be boolean or pending manual')
        complete=all(v is not None for v in values)
        questions.append({'id':qid,'category':items[0]['category'],'results':values,
            'pass_at_1':sum(values)/3 if complete else None,
            'pass_pow_3':all(values) if complete else None,'pass_at_3':any(values) if complete else None,
            'pending_manual':sum(v is None for v in values)})
    def metrics(qs):
        known=all(q['pass_at_1'] is not None for q in qs)
        return {'questions':len(qs),'trials':len(qs)*3,'pending_manual':sum(q['pending_manual'] for q in qs),
            **{key:sum(q[key] for q in qs)/len(qs) if qs and known else None for key in ('pass_at_1','pass_pow_3','pass_at_3')},
            'all_three_correct':sum(q['pass_pow_3'] is True for q in qs),
            'at_least_one_correct':sum(q['pass_at_3'] is True for q in qs)}
    return {'questions':questions,'overall':metrics(questions),
        'by_category':{c:metrics([q for q in questions if q['category']==c]) for c in sorted({q['category'] for q in questions})},
        'definition':'empirical pass@1=three-trial mean; pass^3=all three correct; pass@3=at least one correct; not an unbiased n>k estimator'}


def validate_rehearsal(report,ids):
    if report.get('real_model_calls')!=0 or '替身演练' not in report.get('kind','') or report.get('engineering_errors'):
        raise ValueError('Complete model-double rehearsal with zero engineering errors required')
    summarize_trials(report['cases'])
    if {r['id'] for r in report['cases']}!=set(ids):raise ValueError('Rehearsal workload differs')


def claim_once(path,commit,digest):
    with Path(path).open('x',encoding='utf-8',newline='\n') as f:
        json.dump({'started_at':datetime.now(timezone.utc).isoformat(),'protocol_commit':commit,'protocol_sha256':digest,
            'reruns':0},f,ensure_ascii=False,indent=2);f.write('\n')


def measured_usage(usages,prices):
    # Existing implementation handles provider cache field variants; no estimates.
    from scripts.step12_slots import case_cost
    return case_cost(usages,prices)


def configuration():
    return {**read(ROOT/'evidence/step12_regression_protocol_v2.json')['config'],'SLOT_RESOLUTION':'false'}


def source_hashes():
    paths=[ROOT/p for p in ('config.py','contracts.py','telemetry.py','pyproject.toml')]
    for directory in ('agent','mcp_olist','eval','scripts'):
        paths+=sorted((ROOT/directory).glob('*.py'))
    paths+=sorted((ROOT/'kb').glob('*.md'))
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest() for p in paths}


def paths(suite):
    base='step13_dev_trials' if suite=='dev' else 'step13_'+suite
    return {name:ROOT/'evidence'/f'{base}_{name}.json' for name in ('protocol','started','results','rehearsal')}


def register(suite):
    p=paths(suite);proof=read(p['rehearsal']);questions=workload(suite)
    validate_rehearsal(proof,[q['id'] for q in questions])
    if proof['source_hashes']!=source_hashes():raise ValueError('Source changed after rehearsal')
    source='eval/questions.jsonl' if suite=='dev' else f'eval/step13_{suite}_cases.json'
    protocol={'purpose':'Step13 '+suite+' three independent trials; no tuning',
        'suite':suite,'repetitions':3,'question_ids':[q['id'] for q in questions],
        'planned_trials':len(questions)*3,'question_file':source,'question_file_sha256':sha(ROOT/source),
        'independent_user_per_trial':True,'no_rerun':True,'no_tuning':True,'holdout':False,
        'config':configuration(),'judge':'off','source_hashes':source_hashes(),
        'rehearsal':{'path':p['rehearsal'].relative_to(ROOT).as_posix(),'sha256':sha(p['rehearsal'])},
        'invalidation':'Only a reproducible engineering failure with a failing test committed first may invalidate; wrong answers or low scores never invalidate.',
        'pricing':'Three .env prices required before real run; yuan per million tokens. Missing cache usage/cost stays null.',
        'ordering':'round 1, round 2, round 3; dataset order within round',
        'manual_judgment':'Semantic clarification/coverage cases remain pending human judgment; no regex substitute',
        'review_provenance':'Supplement authored by Claude, gold by Codex, gold reviewed by Claude; cross-model review, not human review' if suite=='supplement' else None}
    if suite=='paired':
        validation=read(ROOT/'evidence/step13_paired_reference_audit.json')
        if not all(r['reference_code_pass'] and r['mutation_killed'] for r in validation['cases']):
            raise ValueError('Paired references/mutations must validate first')
        protocol['reference_validation']={'path':'evidence/step13_paired_reference_audit.json','sha256':sha(ROOT/'evidence/step13_paired_reference_audit.json'),
            'context_sha256':sha(ROOT/'evidence/step13_paired_context.json')}
    if suite=='supplement':
        approved=read(ROOT/'evidence/step13_supplement_reference.json')
        by_id={r['question']['id']:r for r in approved['records']}
        if any(q['gold_sql']!=by_id[q['id']]['question']['gold_sql'] for q in questions):
            raise ValueError('Supplement gold changed after Claude review')
        protocol['reference_validation']={'original_fixture_sha256':sha(ROOT/'evidence/step13_supplement_reference.json'),
            'n08_approved_wording_recheck_sha256':sha(ROOT/'evidence/step13_n08_review.json')}
    with p['protocol'].open('x',encoding='utf-8',newline='\n') as f:json.dump(protocol,f,ensure_ascii=False,indent=2);f.write('\n')
    print(p['protocol'].relative_to(ROOT).as_posix())


def verify_protocol(suite):
    from scripts.step12_regression import require_prices
    p=paths(suite);protocol=read(p['protocol']);prices=require_prices()
    expected=workload(suite)
    if protocol['question_ids']!=[q['id'] for q in expected] or protocol['config']!=configuration() or protocol['repetitions']!=3:
        raise ValueError('Protocol workload/configuration changed')
    if protocol['question_file_sha256']!=sha(ROOT/protocol['question_file']) or protocol['source_hashes']!=source_hashes():
        raise ValueError('Frozen source changed after registration')
    if sha(ROOT/protocol['rehearsal']['path'])!=protocol['rehearsal']['sha256']:raise ValueError('Rehearsal digest mismatch')
    validate_rehearsal(read(ROOT/protocol['rehearsal']['path']),protocol['question_ids'])
    digest=sha(p['protocol']);relative=p['protocol'].relative_to(ROOT).as_posix()
    if shutil.which('git'):
        command=['git','-c',f'safe.directory={ROOT}']
        blob=subprocess.check_output(command+['show','HEAD:'+relative],cwd=ROOT)
        if hashlib.sha256(blob).hexdigest()!=digest:raise ValueError('Protocol not committed exactly')
        commit=subprocess.check_output(command+['log','-1','--format=%H','--',relative],cwd=ROOT,text=True).strip()
        subprocess.run(command+['merge-base','--is-ancestor',commit,'origin/master'],cwd=ROOT,check=True)
    else:
        commit=os.getenv('STEP13_PROTOCOL_COMMIT','')
        if len(commit)!=40 or os.getenv('STEP13_PROTOCOL_SHA256')!=digest:raise ValueError('Missing host-verified pushed protocol ticket')
    if p['started'].exists() or p['results'].exists():raise FileExistsError('Real run already started; no rerun')
    return protocol,commit,prices


def holdout():
    rows=[];sources=[]
    for run,filename,_ in RUNS:
        if not run.startswith('holdout-r'):continue
        data=load_source(ROOT,'evidence/'+filename);sources.append({'run':run,**data['source']})
        rows.extend({'id':c['question_id'],'category':c['category'],'repeat':int(run[-1]),'correct':c['correct'],
            'task_id':c['task_id']} for c in data['summary']['cases'])
    report={'kind':'Read-only saved holdout decisions; no model, SQL or regrading','sources':sources,
        'cases':rows,**summarize_trials(rows)}
    write(ROOT/'evidence/step13_holdout_stability.json',report)
    print(json.dumps(report['overall']))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['holdout','register']);parser.add_argument('--suite',choices=['dev','supplement','paired'],default='dev')
    args=parser.parse_args()
    if args.action=='holdout':holdout()
    else:register(args.suite)
