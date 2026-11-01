"""Review corrections preserve published decisions and historical wording."""
from copy import deepcopy

from eval.step13_errors import read, ROOT


def test_confirmed_evidence_types_and_adjusted_strict_counts():
    from eval.step13_review import adjusted_diagnostics
    original=read(ROOT/'evidence/step13_error_analysis.json')['strict_diagnostics']
    before=deepcopy(original)
    result=adjusted_diagnostics(original)
    issues=[p for r in result for p in r['answer_correct_evidence_problem']]
    assert sum(p['evidence_issue_type']=='checker_false_positive' for p in issues)==18
    assert sum(p['evidence_issue_type']=='real_unsupported' for p in issues)==3
    assert [r['adjusted_strict_correct'] for r in result]==[29,19,20,20,30]
    assert original==before


def test_historical_replay_keeps_every_claim_text_verbatim():
    from eval.step13_review import historical_cases, replay
    rows=historical_cases()
    assert len(rows)==24
    for row in rows:
        result=replay(row)
        assert result['claim_texts']==[c['text'] for c in row['response']['claims']]
        assert result['current_audit']['unsupported_numbers']>=0
        assert result['published_decision_unchanged'] is True


def test_agent_error_reasons_are_specific_not_shared_boilerplate():
    rows=read(ROOT/'eval/step13_error_annotations.json')
    reasons=[r['reason'] for r in rows if r['fairness']=='agent_error']
    assert len(set(reasons))>=12
    assert all('按原公开输出契约或原边界expected' not in reason for reason in reasons)


def test_n08_public_timestamp_requirement_matches_approved_gold():
    rows=read(ROOT/'eval/step13_supplement_cases.json')
    n08=next(q for q in rows if q['id']=='N08')
    assert n08['question'].endswith('按原始时间戳比较,不截断为日期。')
    old=read(ROOT/'evidence/step13_supplement_reference.json')
    saved=next(r for r in old['records'] if r['question']['id']=='N08')
    assert n08['gold_sql']==saved['question']['gold_sql']
