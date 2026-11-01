"""Read-only summaries of committed trial receipts; never run/regrade a model."""
from decimal import Decimal
from pathlib import Path

from eval.step13_errors import ROOT,read,write,sha
from eval.step13_trials import summarize_trials,paths,workload


def totals(rows):
    def total(key):
        values=[r.get(key) for r in rows]
        return sum(values) if all(v is not None for v in values) else None
    inputs=total('input_tokens');cached=total('cached_tokens')
    cost_values=[r.get('cost_yuan_decimal') for r in rows]
    cost=sum((Decimal(v) for v in cost_values),Decimal(0)) if all(v is not None for v in cost_values) else None
    return {'trials':len(rows),'tokens':total('tokens'),'input_tokens':inputs,'cached_tokens':cached,
        'output_tokens':total('output_tokens'),'cache_hit_ratio':cached/inputs if inputs and cached is not None else None,
        'total_cost_yuan_decimal':str(cost) if cost is not None else None,
        'total_cost_yuan':float(cost) if cost is not None else None,
        'average_cost_yuan':float(cost/len(rows)) if cost is not None and rows else None,
        'total_task_elapsed_ms':total('elapsed_ms'),'average_task_elapsed_ms':total('elapsed_ms')/len(rows) if rows and total('elapsed_ms') is not None else None,
        'strict_passed':sum(r.get('strict_pass') is True for r in rows),
        'answer_passed':sum(r.get('correct') is True for r in rows),
        'pending_manual':sum(r.get('correct') is None for r in rows),
        'unknown_usage_trials':[r['id']+':'+str(r['repeat']) for r in rows if r.get('tokens') is None],
        'unknown_cost_trials':[r['id']+':'+str(r['repeat']) for r in rows if r.get('cost_yuan') is None]}


def summarize(suite):
    path=paths(suite)['results'];report=read(path);stats=summarize_trials(report['cases'])
    by_question=[]
    for q in stats['questions']:
        rows=[r for r in report['cases'] if r['id']==q['id']]
        by_question.append({**q,'usage':totals(rows),'trials':[
            {k:r.get(k) for k in ('repeat','correct','strict_pass','task_id','user_id','tokens','input_tokens','cached_tokens',
                'output_tokens','cost_yuan','cost_yuan_decimal','cache_hit_ratio','elapsed_ms','termination','error','manual_status','code_pass','exposure_status')}
            for r in rows]})
    out={'suite':suite,'source_receipt':path.relative_to(ROOT).as_posix(),'source_receipt_sha256':sha(path),
        'source_logs':report['sources'],'metrics':stats,'questions':by_question,'usage':totals(report['cases']),
        'by_category_usage':{c:totals([r for r in report['cases'] if r['category']==c]) for c in stats['by_category']},
        'read_only':True,'model_calls':0,'grading_calls':0}
    if suite=='paired':
        out['pairs']=[{'pair_id':f'P{i:02d}','sides':[
            {'id':f'P{i:02d}{side}',**next(q for q in by_question if q['id']==f'P{i:02d}{side}')}
            for side in 'AB']} for i in range(1,7)]
    write(ROOT/f'evidence/step13_{suite}_summary.json',out)
    return out


def build_suites():
    dev=read(paths('dev')['results']);stats=summarize_trials(dev['cases'])
    regression={q['id'] for q in stats['questions'] if q['pass_pow_3'] is True}
    original=workload('dev')
    reg=[{**q,'source_dataset':'eval/questions.jsonl'} for q in original if q['id'] in regression]
    cap=[{**q,'source_dataset':'eval/questions.jsonl'} for q in original if q['id'] not in regression]
    cap += [{**q,'category':'boundary','split':'boundary','answer_type':'key_facts','required_facts':[],
             'gold_sql':None,'setup_turns':[],'success_kind':'legacy_boundary','manual_required':True,
             'source_dataset':'eval/boundary_cases.json'} for q in read(ROOT/'eval/boundary_cases.json')]
    cap += [{**q,'source_dataset':'eval/step13_paired_cases.json'} for q in workload('paired')]
    write(ROOT/'eval/step13_regression_cases.json',reg)
    write(ROOT/'eval/step13_capability_cases.json',cap)
    out={'selection_receipt':paths('dev')['results'].relative_to(ROOT).as_posix(),'selection_sha256':sha(paths('dev')['results']),
         'regression_ids':[q['id'] for q in reg],'capability_ids':[q['id'] for q in cap],
         'regression_selection_sample_rate':1.0 if reg else None,
         'regression_note':'Selected on these same three trials; 100% is descriptive selection, not an independent future regression validation.',
         'capability_dev':summarize_trials([r for r in dev['cases'] if r['id'] not in regression]) if len(regression)<45 else None,
         'capability_boundary':'Original 10 cases retained; historical result is separate, not pooled across versions or repetitions.',
         'capability_paired':summarize('paired')['metrics'] if paths('paired')['results'].exists() else None,
         'capability_pooled_rate':None,
         'reason_no_pooled_rate':'Different versions/repetition counts for historical boundaries; paired semantic judgments may remain manual.'}
    write(ROOT/'evidence/step13_suite_manifest.json',out)
    return out


def compare_supplement():
    dev=summarize('dev');new=summarize('supplement')
    comparison={'old_dev':dev['metrics']['overall'],'new_supplement':new['metrics']['overall'],
        'pass_at_1_difference_percentage_points':100*(new['metrics']['overall']['pass_at_1']-dev['metrics']['overall']['pass_at_1']),
        'pass_pow_3_difference_percentage_points':100*(new['metrics']['overall']['pass_pow_3']-dev['metrics']['overall']['pass_pow_3']),
        'dev_usage':dev['usage'],'supplement_usage':new['usage'],
        'sources':{r['source_receipt']:r['source_receipt_sha256'] for r in [dev,new]},
        'caveat':'Different question sets, not a controlled causal comparison or statistical significance claim.',
        'authorship':'补充题由Claude出题、Codex写gold、Claude审gold；不同模型交叉审查，不是人工审核。'}
    write(ROOT/'evidence/step13_supplement_vs_dev.json',comparison)
    return comparison


if __name__=='__main__':
    import argparse,json
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['dev','paired','supplement','suites','compare'])
    args=parser.parse_args()
    result=build_suites() if args.action=='suites' else compare_supplement() if args.action=='compare' else summarize(args.action)
    print(json.dumps(result.get('usage',result.get('regression_ids',result.get('pass_at_1_difference_percentage_points'))),ensure_ascii=False))
