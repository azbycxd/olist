"""Three-trial empirical metrics and immutable real-run prerequisites."""
import pytest


def rows():
    return [{'id':qid,'category':qid[0],'repeat':i,'correct':v}
            for qid,values in [('A01',[True,True,True]),('D01',[True,False,False])]
            for i,v in enumerate(values,1)]


def test_empirical_three_trial_metrics_and_suites():
    from eval.step13_trials import summarize_trials
    r=summarize_trials(rows())
    assert r['overall']['pass_at_1']==pytest.approx(4/6)
    assert r['overall']['pass_pow_3']==.5
    assert r['overall']['pass_at_3']==1
    assert [c['id'] for c in r['questions'] if c['pass_pow_3']]==['A01']


@pytest.mark.parametrize('mutation',['missing','duplicate','wrong_repeat'])
def test_reject_incomplete_or_duplicate_trials(mutation):
    from eval.step13_trials import summarize_trials
    sample=rows()
    if mutation=='missing':sample.pop()
    if mutation=='duplicate':sample.append(sample[0])
    if mutation=='wrong_repeat':sample[0]['repeat']=4
    with pytest.raises(ValueError):summarize_trials(sample)


def test_manual_judgment_is_not_silently_counted_as_failure_or_success():
    from eval.step13_trials import summarize_trials
    sample=rows();sample[3]['correct']=None
    result=summarize_trials(sample)
    q=next(q for q in result['questions'] if q['id']=='D01')
    assert q['pass_at_1'] is None and q['pass_pow_3'] is None
    assert result['overall']['pending_manual']==1


def test_real_protocol_requires_all_rehearsal_trials_and_no_errors():
    from eval.step13_trials import validate_rehearsal
    proof={'kind':'模型替身；替身演练，不是成绩','cases':rows(),'real_model_calls':0,'engineering_errors':[]}
    validate_rehearsal(proof,['A01','D01'])
    proof['engineering_errors']=[{'id':'A01','error':'RuntimeError'}]
    with pytest.raises(ValueError):validate_rehearsal(proof,['A01','D01'])


def test_marker_is_exclusive(tmp_path):
    from eval.step13_trials import claim_once
    path=tmp_path/'started.json'
    claim_once(path,'commit','hash')
    with pytest.raises(FileExistsError):claim_once(path,'commit','hash')


def test_unknown_cache_usage_never_invents_cost():
    from eval.step13_trials import measured_usage
    usage=measured_usage([{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}],
        {'TOKEN_PRICE_INPUT':2,'TOKEN_PRICE_CACHED_INPUT':.04,'TOKEN_PRICE_OUTPUT':8})
    assert usage['tokens']==15 and usage['cached_tokens'] is None and usage['cost_yuan'] is None


def test_unchanged_dev_workload_is_45_independent_cases():
    from eval.step13_trials import workload
    questions=workload('dev')
    assert len(questions)==45
    assert all(q['split']=='dev' for q in questions)
    assert len({q['id'] for q in questions})==45
