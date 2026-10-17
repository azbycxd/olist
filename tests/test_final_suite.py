from eval.final_suite import specifications, interval, source_hashes


def test_frozen_manifest_can_be_created_in_evaluation_image():
    hashes=source_hashes()
    assert {'agent/worker.py','eval/run.py','Dockerfile','docker-compose.yml','.env.example'}<=hashes.keys()


def test_dev_ablation_changes_exactly_one_switch():
    specs=dict(specifications('dev'))
    base=specs['dev-final']
    for name,key in [('dev-minus-rag','rag_mode'),('dev-minus-memory','use_memory'),
                     ('dev-minus-gate','number_gate'),('dev-multi-gate','agent_mode')]:
        assert {k for k in base if base[k]!=specs[name][k]}=={'categories',key}
    mask,none=specs['dev-pressure-mask'],specs['dev-pressure-none']
    assert mask['context_limit']==none['context_limit']==6000
    assert {k for k in mask if mask[k]!=none[k]}=={'context_strategy'}


def test_holdout_three_identical_configs_with_isolated_users():
    specs=specifications('holdout')
    assert len(specs)==3 and len({k for k,v in specs})==3
    assert all(v==specs[0][1] and v['user_group'] is None for k,v in specs)
    assert specs[0][1]['split']=='holdout' and specs[0][1]['categories']==list('ABCDE')


def test_interval_preserves_missing_usage_and_zero():
    assert interval([1,None,3]) is None
    assert interval([0,0,0])=={'mean':0,'min':0,'max':0}
    assert interval([2,4,3])=={'mean':3,'min':2,'max':4}
