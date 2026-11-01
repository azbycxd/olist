"""Saved gold results exercise the real independent graders without DB/model access."""
import pytest

from eval.dataset import load_questions


@pytest.mark.parametrize('qid', [q['id'] for q in load_questions()])
def test_saved_reference_passes_both_graders(qid):
    from eval.step13_grader import load_fixture, evaluate
    bundle = load_fixture()
    result = evaluate(bundle, qid)
    assert result['score']['correct']
    assert result['audit']['unsupported_claims'] == 0
    assert result['audit']['unsupported_numbers'] == 0


@pytest.mark.parametrize('mutation', ['offset_5pct','negate_sign','remove_evidence',
    'foreign_evidence','replace_label','unsupported_number'])
def test_mutants_are_killed_by_the_corresponding_grader(mutation):
    from eval.step13_grader import load_fixture, audit_bundle
    report = audit_bundle(load_fixture())
    results = [r for r in report['mutations'] if r['kind'] == mutation and r['applicable']]
    assert results
    assert all(r['killed'] for r in results), [r['id'] for r in results if not r['killed']]


def test_zero_has_no_fake_sign_or_percentage_mutation():
    from eval.step13_grader import mutate, make_record
    q = {'id':'Z','answer_type':'number','required_facts':[], 'question':'zero'}
    rec = make_record(q, [{'value':0}], 'fixture')
    assert mutate(rec, 'offset_5pct', rec)[0] is None
    assert mutate(rec, 'negate_sign', rec)[0] is None


def test_reference_fixture_has_verified_readonly_provenance():
    from eval.step13_grader import load_fixture
    fixture = load_fixture()
    assert len(fixture['records']) == 67
    assert fixture['transaction_read_only'] == 'on'
    assert fixture['database_role'] == 'agent_ro'
    assert fixture['source_log_sha256']
    assert all(r['sql_sha256'] and r['rows'] for r in fixture['records'])


def test_foreign_evidence_is_rejected_even_for_identical_values():
    from eval.step13_grader import make_record, evaluate, mutate
    q = {'id':'X','answer_type':'number','required_facts':[], 'question':'count'}
    a=make_record(q, [{'value':10}], 'fixture')
    b=make_record({**q,'id':'Y'}, [{'value':10}], 'fixture')
    response, _=mutate(a,'foreign_evidence',b)
    result=evaluate({'records':[a,b]},'X',response)
    assert result['score']['correct']
    assert result['audit']['claims'][0]['reason']=='wrong_task'


def test_category_mutation_preserves_original_portuguese_label_domain():
    from eval.step13_grader import load_fixture, mutate
    fixture=load_fixture()
    rec=next(r for r in fixture['records'] if r['question']['id']=='D02')
    response,_=mutate(rec,'replace_label',fixture['records'][0])
    changed=response['claims'][0]['value']['largest_drop_category']
    assert changed in {'beleza_saude','cama_mesa_banho'}
    assert changed != rec['gold']['largest_drop_category']


def test_equivalent_variants_and_ambiguity_cover_saved_questions():
    from eval.step13_grader import load_fixture, audit_bundle
    fixture=load_fixture();report=audit_bundle(fixture)
    assert {r['id'] for r in report['ambiguity']} == {r['question']['id'] for r in fixture['records']}
    assert {r['kind'] for r in report['equivalents']} == {'wide_to_long','date_prose','decline_prose'}
    assert all('public_contract' in r and 'actual_checks' in r for r in report['ambiguity'])


@pytest.mark.parametrize('qid', ['N%02d'%i for i in range(1,13)])
def test_supplement_reference_independent_csv_and_mutants(qid):
    from eval.step13_grader import load_fixture, audit_bundle
    from eval.step13_supplement import load_crosscheck
    fixture=load_fixture('evidence/step13_supplement_reference.json')
    report=audit_bundle(fixture)
    ref=next(r for r in report['references'] if r['id']==qid)
    assert ref['strict_pass']
    assert all(r['killed'] for r in report['mutations'] if r['id']==qid and r['applicable'])
    cross=load_crosscheck()
    case=next(r for r in cross['cases'] if r['id']==qid)
    assert case['consistent'], case


def test_supplement_keeps_supplied_text_and_contract():
    from eval.step13_supplement import verify_supplied_cases
    assert verify_supplied_cases() == 12
