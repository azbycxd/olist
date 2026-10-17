from eval.parameters import distribution


def test_nearest_rank_keeps_missing_observations_explicit():
    assert distribution([None,1,2,3,100])=={'n':4,'missing':1,'p50':2,'p95':100,'max':100}
    assert distribution([None])=={'n':0,'missing':1,'p50':None,'p95':None,'max':None}
