"""Offline historical diagnostics must preserve the published decisions."""
import hashlib
import json

import pytest


def case(correct=True, claims=0, numbers=0, ident='C01'):
    return {'question_id': ident, 'correct': correct,
            'evidence': {'unsupported_claims': claims, 'unsupported_numbers': numbers}}


def test_strict_uses_saved_decisions_and_both_evidence_counts():
    from eval.step13_errors import strict_saved
    rows = [case(), case(numbers=2, ident='C02'), case(False, ident='D01')]
    result = strict_saved(rows)
    assert result['published_correct'] == 2
    assert result['strict_correct'] == 1
    assert [x['question_id'] for x in result['answer_correct_evidence_problem']] == ['C02']
    assert rows[1]['correct'] is True


def test_missing_audit_is_unknown_not_clean():
    from eval.step13_errors import strict_saved
    result = strict_saved([{'question_id':'A01','correct':True}])
    assert result['strict_correct'] == 0
    assert result['unknown_audit'] == ['A01']


def test_no_claims_is_not_invented_evidence_failure():
    from eval.step13_errors import strict_saved
    assert strict_saved([case()])['strict_correct'] == 1


def test_source_rejects_changed_log(tmp_path):
    from eval.step13_errors import load_source
    (tmp_path/'logs').mkdir(); (tmp_path/'evidence').mkdir()
    raw=b'{"event":"test"}\n';(tmp_path/'logs/a.jsonl').write_bytes(raw)
    summary={'source_log':'a.jsonl','source_log_sha256':hashlib.sha256(raw).hexdigest(),'cases':[case()]}
    (tmp_path/'evidence/a.json').write_text(json.dumps(summary))
    assert len(load_source(tmp_path, 'evidence/a.json')['events']) == 1
    (tmp_path/'logs/a.jsonl').write_bytes(raw+b'\n')
    with pytest.raises(ValueError,match='hash'):
        load_source(tmp_path, 'evidence/a.json')


def test_classification_requires_exact_coverage():
    from eval.step13_errors import summarize_failures
    with pytest.raises(ValueError,match='coverage'):
        summarize_failures([], {'run:D01'})


def test_grader_or_ambiguity_diagnosis_requires_concrete_evidence():
    from eval.step13_errors import summarize_failures
    row={'trial_id':'run:D01','category':'shape','fairness':'grader_issue','support':[]}
    with pytest.raises(ValueError,match='evidence'):
        summarize_failures([row], {'run:D01'})


def test_category_table_counts_trials_not_distinct_questions():
    from eval.step13_errors import summarize_failures
    rows=[{'trial_id':f'r{i}:D01','category':'shape','fairness':'agent_error','support':['public keys']} for i in range(3)]
    table=summarize_failures(rows,{r['trial_id'] for r in rows})
    assert table['total'] == 3
    assert table['categories'][0]['count'] == 3
    assert table['categories'][0]['share'] == 1


def test_more_than_eight_categories_is_rejected():
    from eval.step13_errors import summarize_failures
    rows=[{'trial_id':str(i),'category':str(i),'fairness':'agent_error','support':[]} for i in range(9)]
    with pytest.raises(ValueError,match='eight'):
        summarize_failures(rows,{r['trial_id'] for r in rows})
