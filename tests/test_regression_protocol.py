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
