import asyncio
import json
from types import SimpleNamespace
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
