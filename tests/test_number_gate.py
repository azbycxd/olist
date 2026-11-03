import asyncio
import json
from types import SimpleNamespace

import pytest

from contracts import Claim
from agent import number_gate as gate


def test_scan_sign_units_identifiers_and_structured_values():
    claims=[Claim(text='delta',value={'change_pct':-5,'gmv':10000},evidence=[])]
    value={'report':'2017 年下降 5%，减少 -5%；金额 1 万，虚构 66。','rows':[{'v':66}]}
    clean,bad=gate.scan(value,claims,True)
    assert bad==['66','66']
    assert clean['rows']==[{'v':'未验证'}]
    assert '下降 5%' in clean['report'] and '1 万' in clean['report']


def test_only_one_rewrite_then_replace_even_new_hallucinations(monkeypatch):
    calls=[];events=[]
    async def request(*args,**kwargs):
        calls.append(args)
        assert '99' in args[2][1]['content']
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({'answer':'仍有 88，下降 5%'})))])
    monkeypatch.setattr(gate,'request',request)
    claims=[Claim(text='delta',value=-5,evidence=[])]
    result=asyncio.run(gate.enforce('虚构 99',claims,None,'model',lambda *a:events.append(a)))
    assert len(calls)==1 and result=='仍有 未验证，下降 5%'
    assert events[-1][1]['replaced']==['88']


def test_failed_rewrite_fails_closed(monkeypatch):
    async def request(*a,**k):raise RuntimeError('unavailable')
    monkeypatch.setattr(gate,'request',request)
    assert asyncio.run(gate.enforce(999,[],None,'m',lambda *a:None))=='未验证'


def test_single_approval_rejects_cross_row_and_bad_references():
    ref='12345678-1234-1234-1234-123456789012'
    class Remote:
        async def call(self,*a):return {'result_id':ref,'data_version':'v','preview':[{'state':'SP','n':5},{'state':'RJ','n':9}]}
    claims=[Claim(text='ok',value={'state':'SP','n':5},evidence=[ref]),
            Claim(text='bad',value={'state':'SP','n':9},evidence=[ref])]
    assert asyncio.run(gate.approve_values(claims,Remote()))==claims[:1]


def test_leading_decimal_is_not_a_list_ordinal():
    from eval.checker import report_numbers
    claims=[Claim(text='amount',value=181968.09,evidence=[])]
    assert gate.scan(181968.09,claims)==(181968.09,[])
    assert gate.scan('181968.09',claims)==('181968.09',[])
    assert report_numbers('181968.09')==[gate.Decimal('181968.09')]
    assert gate.scan('1. GMV 181968.09',claims)[1]==[]


@pytest.mark.parametrize('case,approved', [
    ('empty_evidence', False),
    ('fetch_exception', False),
    ('returned_error', False),
    ('wrong_result_id', False),
    ('empty_version', False),
    ('different_versions', False),
    ('same_versions', True),
])
def test_approval_requires_valid_consistent_evidence(case, approved):
    first = '12345678-1234-1234-1234-123456789012'
    second = '12345678-1234-1234-1234-123456789013'
    evidence = [] if case == 'empty_evidence' else [first]
    if case in {'different_versions', 'same_versions'}:
        evidence.append(second)
    claim = Claim(text='orders', value={'n': 5}, evidence=evidence)

    class Remote:
        async def call(self, name, args):
            if case == 'fetch_exception':
                raise RuntimeError('unavailable')
            result = {'result_id': args['result_id'], 'data_version': 'v1', 'preview': [{'n': 5}]}
            if case == 'returned_error':
                result['error'] = 'unavailable'
            elif case == 'wrong_result_id':
                result['result_id'] = second
            elif case == 'empty_version':
                result['data_version'] = ''
            elif case == 'different_versions' and args['result_id'] == second:
                result['data_version'] = 'v2'
            return result

    assert asyncio.run(gate.approve_values([claim], Remote())) == ([claim] if approved else [])


def test_supported_answer_skips_rewrite_and_emits_empty_event(monkeypatch):
    calls = []
    events = []

    async def request(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError('Supported answers must not request a rewrite')

    monkeypatch.setattr(gate, 'request', request)
    answer = {'orders': 5}
    claims = [Claim(text='orders', value=5, evidence=[])]
    result = asyncio.run(gate.enforce(answer, claims, None, 'model', lambda *args: events.append(args)))
    assert result is answer
    assert calls == []
    assert events == [('number_gate', {'before': [], 'after_rewrite': [], 'replaced': [], 'rewrites': 0})]


@pytest.mark.parametrize('content,error', [
    (None, None),
    ('not JSON', 'JSONDecodeError'),
    ('[1]', None),
    ('{"answer":"x","k":1}', None),
    ('{"answer":NaN}', 'ValueError'),
])
def test_invalid_rewrite_preserves_original_for_replacement(monkeypatch, content, error):
    calls = []
    events = []

    async def request(*args, **kwargs):
        calls.append((args, kwargs))
        if content is None:
            return None
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    monkeypatch.setattr(gate, 'request', request)
    result = asyncio.run(gate.enforce('虚构 99', [], None, 'model', lambda *args: events.append(args)))
    assert result == '虚构 未验证'
    assert len(calls) == 1
    expected = [('number_gate_rewrite_failed', {'error': error})] if error else []
    expected.append(('number_gate', {
        'before': ['99'], 'after_rewrite': ['99'], 'replaced': ['99'], 'rewrites': 1,
    }))
    assert events == expected


@pytest.mark.parametrize('value,text,accepted', [
    (5, '5.04', True),
    (5, '5.06', False),
    (0, '0.00000001', True),
    (0, '0.00000002', False),
])
def test_scan_relative_and_absolute_tolerance(value, text, accepted):
    claims = [Claim(text='amount', value=value, evidence=[])]
    expected = (text, []) if accepted else ('未验证', [text])
    assert gate.scan(text, claims, True) == expected


@pytest.mark.parametrize('text,value', [
    ('30.5万', 305000),
    ('1.2亿', 120000000),
    ('3千', 3000),
    ('1e3', 1000),
])
def test_scan_units_and_scientific_notation(text, value):
    claims = [Claim(text='amount', value=value, evidence=[])]
    assert gate.scan(text, claims, True) == (text, [])


def test_scan_preserves_uuid_without_claims():
    ref = '12345678-1234-1234-1234-123456789012'
    assert gate.scan(ref, [], True) == (ref, [])
