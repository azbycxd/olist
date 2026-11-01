"""Read saved decisions; never execute SQL, a model, or a historical grader.

Event order locates an observed upstream mistake, not a scoring criterion.
Human-readable annotations are Codex diagnoses awaiting human spot checks.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = [
    ('step9-dev-final', 'eval_step9-dev-final_20261017T102853Z_45a71d7d.summary.json', None),
    ('holdout-r1', 'eval_step9-holdout-r1_20261017T104235Z_7648ab8d.summary.json', None),
    ('holdout-r2', 'eval_step9-holdout-r2_20261017T104451Z_7e1a9d1a.summary.json', None),
    ('holdout-r3', 'eval_step9-holdout-r3_20261017T104707Z_e9d273ef.summary.json', None),
    ('step12-v2', 'eval_step12-regression-v2-once_20261028T011034Z_c949fe88.summary.json', None),
    ('slot-dev', 'eval_step12-slot-once_20261028T045020Z_5df1fb4e.summary.json', None),
    ('slot-boundary', 'eval_step12-slot-once-boundary_20261028T045332Z_f52ef925.summary.json', 'step12_slot_boundary_review.json'),
    ('original-boundary', 'eval_step10-boundary_20261017T110935Z_62bc557e.summary.json', 'step10_boundary_review.summary.json'),
]
FAIRNESS = {'agent_error', 'grader_issue', 'task_ambiguity', 'environment'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, obj):
    with Path(path).open('w', encoding='utf-8', newline='\n') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write('\n')


def load_source(root, relative):
    path = root / relative
    summary = read(path)
    log = root / 'logs' / summary['source_log']
    if sha(log) != summary['source_log_sha256']:
        raise ValueError('Source log hash mismatch: ' + str(log))
    events = [{'line':i, **json.loads(line)} for i,line in
              enumerate(log.read_text(encoding='utf-8').splitlines(), 1) if line.strip()]
    return {'summary':summary, 'events':events, 'source':{
        'receipt':relative, 'receipt_sha256':sha(path),
        'log':log.relative_to(root).as_posix(), 'log_sha256':sha(log)}}


def strict_saved(cases):
    correct = strict = 0
    unknown, problems = [], []
    for case in cases:
        correct += case['correct'] is True
        audit = case.get('evidence', {})
        counts = [audit.get(k) for k in ('unsupported_claims','unsupported_numbers')]
        if any(type(n) is not int or n < 0 for n in counts):
            unknown.append(case['question_id'])
        elif case['correct'] is True:
            if any(counts):
                problems.append({'question_id':case['question_id'],
                    'unsupported_claims':counts[0], 'unsupported_numbers':counts[1],
                    'saved_response':case.get('response'), 'saved_evidence':audit})
            else:
                strict += 1
    total = len(cases)
    return {'total':total, 'published_correct':correct, 'strict_correct':strict,
            'published_accuracy':correct/total if total else None,
            'strict_rate':strict/total if total else None,
            'unknown_audit':unknown, 'answer_correct_evidence_problem':problems}


def summarize_failures(rows, expected_ids):
    actual = [r['trial_id'] for r in rows]
    if len(set(actual)) != len(actual) or set(actual) != expected_ids:
        raise ValueError('Failure annotation coverage differs from saved failures')
    counts = Counter(r['category'] for r in rows)
    if len(counts) > 8:
        raise ValueError('At most eight failure categories are permitted')
    for row in rows:
        if row['fairness'] not in FAIRNESS:
            raise ValueError('Unknown fairness classification')
        if row['fairness'] in {'grader_issue','task_ambiguity'} and not row.get('support'):
            raise ValueError('Grader/ambiguity claims require concrete evidence')
    return {'total':len(rows), 'categories':[
        {'category':key, 'count':n, 'share':n/len(rows),
         'fairness':dict(Counter(r['fairness'] for r in rows if r['category']==key)),
         'examples':[r['trial_id'] for r in rows if r['category']==key]}
        for key,n in counts.items()],
        'fairness':{key:sum(r['fairness']==key for r in rows) for key in sorted(FAIRNESS)}}


def historical_runs(root=ROOT):
    for name, filename, review in RUNS:
        data = load_source(root, 'evidence/'+filename)
        if review:
            rv = read(root/'evidence'/review)
            expected = rv.get('source_sha256', rv.get('source_receipt_sha256'))
            if expected != data['source']['receipt_sha256']:
                raise ValueError('Boundary review hash mismatch')
            judgments = {c['id']:c for c in rv['cases']}
            if set(judgments) != {c['id'] for c in data['summary']['cases']}:
                raise ValueError('Boundary review coverage mismatch')
            data['review'] = judgments
            data['review_source'] = {'path':'evidence/'+review,'sha256':sha(root/'evidence'/review)}
        yield name, data


def build(root=ROOT):
    annotations = read(root/'eval/step13_error_annotations.json')
    open_notes = read(root/'evidence/step13_error_open_notes.json')
    saved_path = root/'evidence/step13_saved_query_results.json'
    saved = read(saved_path)
    strict_notes = read(root/'eval/step13_strict_notes.json')
    failures, sources, strict = [], [], []
    expected = set()
    for name, run in historical_runs(root):
        summary=run['summary'];sources.append({'run':name,**run['source'],
            'case_count':len(summary['cases']), 'review':run.get('review_source')})
        if name in {'step9-dev-final','holdout-r1','holdout-r2','holdout-r3','step12-v2'}:
            diagnostic = strict_saved(summary['cases'])
            for problem in diagnostic['answer_correct_evidence_problem']:
                problem['diagnosis'] = strict_notes[name+':'+problem['question_id']]
            strict.append({'run':name, 'source':run['source'], **diagnostic})
        for c in summary['cases']:
            qid=c.get('question_id',c.get('id'));key=name+':'+qid
            failed=(not run['review'][qid]['passed']) if 'review' in run else c['correct'] is False
            if not failed:continue
            expected.add(key)
            note=next((a for a in annotations if a['trial_id']==key),None)
            if note is None:raise ValueError('Missing annotation '+key)
            history=[e for e in run['events'] if e.get('task_id')==c['task_id']]
            anchor=next((e for e in history if e['line']==note['first_observed']['log_line']),None)
            if anchor is None:raise ValueError('Upstream anchor is not part of trial '+key)
            failures.append({**note,'question_id':qid,'run':name,'source':run['source'],
                'task_id':c['task_id'],'original_case':c,
                'original_review':run.get('review',{}).get(qid),
                'original_oracle_value':summary.get('oracle_values',{}).get(qid),
                'first_observed_event':anchor,'event_count':len(history),
                'trajectory':history,
                'saved_queries':[r for r in saved['records'] if r['task_id']==c['task_id']],
                'open_observation':next(a for a in open_notes if a['trial_id']==key)['observation']})
    tally=summarize_failures(failures,expected)
    report={'kind':'read-only historical diagnostic; no rescoring, model or business SQL calls',
        'reviewer':'分类由Codex完成，待人工抽查',
        'scope':'Named final-configuration runs plus slot experiment and original Step10 boundary run',
        'excluded':'Step11 initial/target boundary candidates had non-adopted BOUNDARY_GUARDS behavior; ablations, v1 engineering-invalid run and model doubles excluded. Published scores unchanged.',
        'sources':sources,'open_notes_sha256':sha(root/'evidence/step13_error_open_notes.json'),
        'annotations_sha256':sha(root/'eval/step13_error_annotations.json'),
        'saved_result_export':{'path':'evidence/step13_saved_query_results.json','sha256':sha(saved_path),
            'note':'One read-only Agent database export of existing query_results; no business SQL re-execution'},
        'counts':tally,'failures':failures,'strict_diagnostics':strict,
        'model_calls':0,'database_calls':0,
        'strict_definition':'saved correct == true AND saved unsupported_claims == 0 AND saved unsupported_numbers == 0; missing audit is unknown; does not replace any published score'}
    write(root/'evidence/step13_error_analysis.json', report)
    print(json.dumps({'failed_trials':tally['total'],'categories':len(tally['categories']),
        'fairness':tally['fairness'],'strict':[(r['run'],r['published_correct'],r['strict_correct'],r['total']) for r in strict]},ensure_ascii=False))
    return report


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    build()
