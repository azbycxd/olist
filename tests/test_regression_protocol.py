"""The Step12 regression is dev-only and cannot silently run twice."""
import json
import pytest


def protocol(tmp_path):
    path=tmp_path/'protocol.json'
    path.write_text(json.dumps({'split':'dev','categories':['C','D','E'],'runs':1,'holdout':False,
        'independent_user_per_question':True,'no_rerun':True,'no_tuning':True,'pass':{'C':17,'D':6,'E':6},
        'config':{'SLOT_RESOLUTION':'false','CONTEXT_PREFLIGHT':'false','AGENT_MODE':'single'}}))
    return path


def test_regression_marker_is_exclusive(tmp_path):
    from scripts.step12_regression import claim_once
    path=protocol(tmp_path);marker=tmp_path/'started.json'
    claim_once(path,marker)
    with pytest.raises(FileExistsError):claim_once(path,marker)


def test_regression_rejects_holdout_and_repeats(tmp_path):
    from scripts.step12_regression import claim_once
    path=protocol(tmp_path)
    for changes in ({'split':'holdout'},{'runs':2},{'independent_user_per_question':False}):
        value=json.loads(path.read_text());value.update(changes);path.write_text(json.dumps(value))
        with pytest.raises(ValueError):claim_once(path,tmp_path/'never-started.json')
        assert not (tmp_path/'never-started.json').exists()


def test_host_verified_protocol_ticket_for_images_without_git(tmp_path,monkeypatch):
    import hashlib
    from scripts.step12_regression import verify_committed_protocol
    path=protocol(tmp_path)
    monkeypatch.setattr('shutil.which',lambda _:None)
    monkeypatch.setenv('STEP12_PROTOCOL_COMMIT','a'*40)
    monkeypatch.setenv('STEP12_PROTOCOL_SHA256','incorrect')
    with pytest.raises(ValueError):verify_committed_protocol(path,tmp_path)
    monkeypatch.setenv('STEP12_PROTOCOL_SHA256',hashlib.sha256(path.read_bytes()).hexdigest())
    assert verify_committed_protocol(path,tmp_path)=='a'*40


def test_v2_paths_cannot_overwrite_v1(tmp_path):
    from scripts.step12_regression import version_paths
    paths=version_paths(tmp_path,2)
    assert [p.name for p in paths]==['step12_regression_protocol_v2.json','step12_regression_started_v2.json','step12_regression_results_v2.json']


@pytest.mark.parametrize('missing_value',[None,'','NaN','Infinity','-1'])
def test_v2_requires_all_three_prices_before_start(monkeypatch,missing_value):
    from scripts.step12_regression import require_prices
    for key in ['TOKEN_PRICE_INPUT','TOKEN_PRICE_CACHED_INPUT','TOKEN_PRICE_OUTPUT']:monkeypatch.setenv(key,'1.25')
    if missing_value is None:monkeypatch.delenv('TOKEN_PRICE_CACHED_INPUT')
    else:monkeypatch.setenv('TOKEN_PRICE_CACHED_INPUT',missing_value)
    with pytest.raises(ValueError,match='TOKEN_PRICE_CACHED_INPUT'):require_prices()
    monkeypatch.setenv('TOKEN_PRICE_CACHED_INPUT','0')
    assert require_prices()['TOKEN_PRICE_CACHED_INPUT']==0


def test_git_verification_uses_v2_protocol_path(tmp_path,monkeypatch):
    from scripts.step12_regression import verify_committed_protocol
    path=tmp_path/'evidence'/'step12_regression_protocol_v2.json';path.parent.mkdir();path.write_text('{}')
    monkeypatch.setattr('shutil.which',lambda _:True)
    calls=[]
    def output(args,**kw):
        calls.append(args)
        return 'a'*40+'\n' if '--format=%H' in args else b'{}'
    monkeypatch.setattr('subprocess.check_output',output)
    assert verify_committed_protocol(path,tmp_path)=='a'*40
    assert 'HEAD:evidence/step12_regression_protocol_v2.json' in calls[0]
