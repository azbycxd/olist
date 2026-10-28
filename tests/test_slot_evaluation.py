"""The slot experiment must rehearse both entrances and freeze adoption rules."""
import json
from pathlib import Path

import pytest


def rows():
    return [{'id': f'{cat}{i:02}', 'category': cat, 'correct': True} for cat,n in (('C',17),('D',8),('E',6)) for i in range(1,n+1)]


def test_adoption_requires_all_four_fixed_thresholds():
    from scripts.step12_slots import decide
    dev = rows()
    boundary = [{'id':f'X{i:02}', 'passed': i<=8, 'reason':'saved-response review'} for i in range(1,11)]
    assert decide(dev, boundary)['adopt'] is True
    dev[17]['correct'] = dev[18]['correct'] = False
    assert decide(dev, boundary)['adopt'] is True  # D 6/8 is sufficient.
    for index in (0,19,25):
        bad = [dict(r) for r in dev]; bad[index]['correct'] = False
        assert decide(bad, boundary)['adopt'] is False
    boundary[7]['passed'] = False
    assert decide(dev, boundary)['adopt'] is False
    with pytest.raises(ValueError): decide(dev[:-1], boundary)
    with pytest.raises(ValueError): decide(dev, boundary[:-1])
    with pytest.raises(ValueError): decide(dev, [boundary[0]]*10)


def test_plan_freezes_all_entrances_flags_prices_and_invalidation_rules():
    from scripts.step12_slots import validate_plan, slot_configuration
    from config import ROOT
    config=slot_configuration(ROOT)
    assert config['SLOT_RESOLUTION']=='true' and config['BOUNDARY_GUARDS']=='false'
    plan={'split':'dev','categories':['C','D','E'],'runs':1,'holdout':False,
          'independent_user_per_question':True,'no_rerun':True,'no_tuning':True,
          'pass':{'C':17,'D':6,'E':6,'boundary':8},'boundary_suite':'step11-original',
          'boundary_runs':1,'config':config,
          'invalidation':{'reproducible_engineering_failure':True,'failing_test_committed_first':True,'wrong_answers_do_not_invalidate':True}}
    validate_plan(plan, ROOT)
    for changed in ({'pass':{**plan['pass'],'boundary':7}}, {'boundary_runs':2}, {'holdout':True},
                    {'config':{**config,'SLOT_RESOLUTION':'false'}}, {'config':{**config,'TOKEN_PRICE_INPUT':'0'}},
                    {'invalidation':{}}):
        with pytest.raises(ValueError):validate_plan({**plan,**changed}, ROOT)


def test_rehearsal_requires_41_cases_slots_and_parallel_sql_or_zero_call_clarification():
    from scripts.step12_slots import validate_rehearsal
    dev_ids=[r['id'] for r in rows()]; boundary_ids=[f'X{i:02}' for i in range(1,11)]
    cases=[{'id':i,'task_id':i,'user_id':i,'termination':'final_answer','error':None,
            'slot_events':1,'clarification':False,'sql_events':2,'model_calls':3} for i in dev_ids+boundary_ids]
    cases[-1].update(clarification=True,sql_events=0,model_calls=0)
    report={'kind':'模型替身；替身演练，不是成绩','real_model_calls':0,'dev':cases[:31],'boundary':cases[31:]}
    validate_rehearsal(report,dev_ids,boundary_ids)
    for key,value in [('error','UniqueViolation'),('slot_events',0),('sql_events',0),('user_id',cases[1]['user_id'])]:
        bad=json.loads(json.dumps(report));bad['dev'][0][key]=value
        with pytest.raises(ValueError):validate_rehearsal(bad,dev_ids,boundary_ids)
    bad=json.loads(json.dumps(report));bad['boundary'][-1]['model_calls']=1
    with pytest.raises(ValueError):validate_rehearsal(bad,dev_ids,boundary_ids)


def test_zero_call_cost_and_unknown_cache_are_distinct():
    from scripts.step12_slots import case_cost
    prices={'TOKEN_PRICE_INPUT':2,'TOKEN_PRICE_CACHED_INPUT':.04,'TOKEN_PRICE_OUTPUT':8}
    zero=case_cost([],prices)
    assert zero['tokens']==zero['cost_yuan']==0 and zero['cache_hit_ratio'] is None
    known=case_cost([{'prompt_tokens':1000,'completion_tokens':50,'total_tokens':1050,'prompt_cache_hit_tokens':800}],prices)
    assert known['cache_hit_ratio']==.8 and known['cost_yuan']==pytest.approx(.000832)
    unknown=case_cost([{'prompt_tokens':1000,'completion_tokens':50,'total_tokens':1050}],prices)
    assert unknown['tokens']==1050 and unknown['cached_tokens'] is None and unknown['cost_yuan'] is None


def test_v2_comparison_keeps_both_directions_and_actual_deltas():
    from scripts.step12_slots import compare_v2
    old=[{'id':'C01','correct':True,'tokens':100,'cost_yuan':.1}, {'id':'D02','correct':False,'tokens':200,'cost_yuan':.2}]
    new=[{'id':'C01','correct':False,'tokens':150,'cost_yuan':.15}, {'id':'D02','correct':True,'tokens':180,'cost_yuan':.18}]
    report=compare_v2(old,new)
    assert report['pass_to_fail']==['C01'] and report['fail_to_pass']==['D02']
    assert report['cases'][0]['token_delta']==50
    assert report['cases'][1]['cost_delta_yuan']==pytest.approx(-.02)
    with pytest.raises(ValueError):compare_v2(old,new[:-1])


def test_slot_start_marker_is_atomic_and_separate_from_v2(tmp_path):
    from scripts.step12_slots import claim_marker
    v2=tmp_path/'step12_regression_started_v2.json';v2.write_text('preserve')
    marker=tmp_path/'step12_slot_started.json'
    claim_marker(marker,'a'*40,'b'*64,'real model')
    with pytest.raises(FileExistsError):claim_marker(marker,'a'*40,'b'*64,'real model')
    assert v2.read_text()=='preserve'
