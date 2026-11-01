"""Confirmed review diagnoses and exact historical wording, never score old answers."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from contracts import FinalAnswer
from eval.checker import check
from eval.step13_errors import ROOT, read, write, sha, historical_runs


def adjusted_diagnostics(diagnostics):
    result=deepcopy(diagnostics)
    for run in result:
        false_positives=0
        for issue in run['answer_correct_evidence_problem']:
            real=issue['question_id']=='A08'
            issue['evidence_issue_type']='real_unsupported' if real else 'checker_false_positive'
            issue['classification_authority']='用户本轮复核确认；不改原评分器输出和发布成绩'
            issue['evidence_issue_basis']=('正文共5种来自模型自行数列表；保存SQL只有支付方式列表，没有数量结果。' if real else issue['diagnosis'])
            false_positives+=not real
        run['adjusted_strict_correct']=run['strict_correct']+false_positives
        run['adjusted_strict_rate']=run['adjusted_strict_correct']/run['total']
    return result


def historical_cases():
    diagnostic=read(ROOT/'evidence/step13_error_analysis.json')
    selected={r['run']+':'+p['question_id'] for r in diagnostic['strict_diagnostics']
              for p in r['answer_correct_evidence_problem']}
    selected.update({'step9-dev-final:D07','slot-dev:D01','slot-dev:D08'})
    cases=[]
    for run,data in historical_runs():
        for case in data['summary']['cases']:
            key=run+':'+case.get('question_id',case.get('id'))
            if key in selected:
                cases.append({'trial_id':key,'question_id':case.get('question_id',case.get('id')),
                    'task_id':case['task_id'],'data_version':data['summary']['data_version'],
                    'response':case['response'],'saved_audit':case['evidence'],'source':data['source'],
                    'issue_type':'real_unsupported' if key.endswith(':A08') else 'checker_false_positive'})
    return cases


def export_results():
    """Fetch existing saved evidence only; no model or business SQL execution."""
    import psycopg
    from psycopg.types.json import Jsonb
    from config import db_kwargs
    rows=historical_cases()
    ids=sorted({ref for row in rows for claim in row['response']['claims'] for ref in claim['evidence']})
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        conn.execute('SET TRANSACTION READ ONLY')
        saved=conn.execute('SELECT result_id,task_id,data_version,sql,rows FROM query_results WHERE result_id=ANY(%s::uuid[])',(ids,)).fetchall()
    store={str(r[0]):{'task_id':str(r[1]),'data_version':r[2],'sql':r[3],'rows':r[4]} for r in saved}
    if set(store)!=set(ids):raise ValueError('Missing historical evidence; do not fabricate grounding')
    log=ROOT/'logs/step13_review_saved_results.jsonl'
    if log.exists():raise FileExistsError(log)
    with log.open('w',encoding='utf-8',newline='\n') as f:
        for rid,result in store.items():f.write(json.dumps({'result_id':rid,**result},ensure_ascii=False)+'\n')
    write(ROOT/'evidence/step13_review_saved_results.json',{'results':store,
        'read_only':True,'source_log':log.relative_to(ROOT).as_posix(),'source_log_sha256':sha(log)})


def replay(row):
    store=read(ROOT/'evidence/step13_review_saved_results.json')['results']
    fetch=lambda ids:{i:store[i] for i in ids if i in store}
    response=FinalAnswer.model_validate(row['response'])
    audit=check(response,fetch,row['task_id'],row['data_version'])
    per_claim=[]
    for claim in response.claims:
        one=check(FinalAnswer(answer='',claims=[claim]),fetch,row['task_id'],row['data_version'])
        per_claim.append({'text':claim.text,'text_sha256':hashlib.sha256(claim.text.encode()).hexdigest(),'audit':one})
    remaining=sum(c['audit']['unsupported_numbers'] for c in per_claim)
    state=('real_unsupported_still_detected' if remaining else 'real_unsupported_no_longer_detected') if row['issue_type']=='real_unsupported' else ('false_positive_still_present' if remaining else 'historical_false_positive_now_fixed')
    return {**row,'claim_texts':[c.text for c in response.claims],
        'current_audit':audit,'per_claim_text':per_claim,'claim_text_unsupported_numbers':remaining,
        'diagnostic_state':state,'published_decision_unchanged':True,
        'note':'仅复测证据扫描；无score调用；不替换原audit、原correct或历史严格率'}


def run():
    rows=[replay(row) for row in historical_cases()]
    path=ROOT/'logs/step13_review_text_replay.jsonl'
    with path.open('w',encoding='utf-8',newline='\n') as f:
        for row in rows:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    report={'kind':'exact historical claim.text replay against current checker; diagnostic only',
        'cases':rows,'model_calls':0,'business_sql_calls':0,'historical_answer_scores_changed':0,
        'checker_sha256':sha(ROOT/'eval/checker.py'),'saved_results_sha256':sha(ROOT/'evidence/step13_review_saved_results.json'),
        'source_log':path.relative_to(ROOT).as_posix(),'source_log_sha256':sha(path)}
    write(ROOT/'evidence/step13_historical_text_replay.json',report)
    print(json.dumps([(r['trial_id'],r['diagnostic_state'],r['claim_text_unsupported_numbers']) for r in rows],ensure_ascii=False))


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--export',action='store_true');args=parser.parse_args()
    if args.export:export_results()
    else:run()
