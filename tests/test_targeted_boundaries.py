import asyncio
import ast
from datetime import date,datetime
from types import SimpleNamespace
import zipfile

import pytest
from config import ROOT,dimension_precheck_enabled
from agent.boundaries import CLARIFY,context,date_ranges,prepare_context,make_assumption_explicit
from agent.number_gate import scan
from agent.retrieval import ToolView
from contracts import FinalAnswer,Claim
from mcp_olist.boundaries import coverage
from eval.step11_targeted import acceptance

PROFILE={'coverage':coverage(datetime(2016,9,4,21,15,19),datetime(2018,10,17,17,30,18))}


@pytest.mark.parametrize('question,warning',[
    ('2017年客户数',False),('比较2018年Q1、Q2的GMV',False),
    ('2018年第二季度订单数',False),('2018 年一季度时效',False),
    ('2018年上半年',False),('2018-10-17 的订单',False),
    ('2016-09-04 至 2018-10-17',False),('2017年2月3日',False),
    ('2018年Q1和Q4',True),('2016全年',True),('2018 年完整全年',True),
    ('2015年，如查不到改用2016年完整全年',True),('2016年9月',True),
    ('2018-10-18',True),('2028年第一季度',True),
    ('今年的订单',True),('销售额多少',False),
])
def test_only_out_of_range_injects_one_line(monkeypatch,question,warning):
    monkeypatch.setenv('BOUNDARY_GUARDS','true')
    lines=context(question,PROFILE).strip().splitlines()
    assert lines[0]==CLARIFY and len(lines)==(2 if warning else 1)
    if not warning:assert '2016-09-04' not in lines[0] and 'coverage' not in lines[0]


def test_date_detection_uses_generic_intervals_and_relative_clock():
    assert date_ranges('2018年Q1、Q2')==[(date(2018,1,1),date(2018,3,31)),(date(2018,4,1),date(2018,6,30))]
    assert date_ranges('上月',date(2025,1,5))==[(date(2024,12,1),date(2024,12,31))]
    assert date_ranges('2017-10-31')==[(date(2017,10,31),date(2017,10,31))]


def test_fallback_has_no_boundary_prompt_or_extra_tool_definitions(monkeypatch):
    monkeypatch.setenv('BOUNDARY_GUARDS','false')
    monkeypatch.delenv('DIMENSION_PRECHECK',raising=False)
    assert dimension_precheck_enabled()
    class NeverCalled:
        async def call(self,*args):raise AssertionError('No blanket metadata bootstrap in fallback')
    assert asyncio.run(prepare_context('2028年',NeverCalled(),lambda *args:None))==''
    response=FinalAnswer(answer=42,claims=[])
    assert make_assumption_explicit(response,'销售额')==response
    names=['run_sql','describe_table','data_context','check_dimension','state_read','state_write']
    remote=SimpleNamespace(tools=[{'function':{'name':n}} for n in names])
    assert [t['function']['name'] for t in ToolView(remote).tools]==['run_sql','describe_table']


def test_no_date_question_does_not_fetch_metadata(monkeypatch):
    monkeypatch.setenv('BOUNDARY_GUARDS','true')
    class NeverCalled:
        async def call(self,*args):raise AssertionError('No dates to compare')
    assert asyncio.run(prepare_context('GMV多少',NeverCalled(),lambda *args:None)).strip()==CLARIFY


def test_fallback_matches_frozen_step9_prompt_contract_and_gate(monkeypatch):
    monkeypatch.setenv('BOUNDARY_GUARDS','false')
    from agent.loop import SYSTEM
    from agent.tools import FINAL_TOOL
    with zipfile.ZipFile(ROOT/'evidence/step9_holdout_frozen_source.zip') as z:
        for name,key,value in [('agent/loop.py','SYSTEM',SYSTEM),('agent/tools.py','FINAL_TOOL',FINAL_TOOL)]:
            tree=ast.parse(z.read(name).decode())
            node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==key for t in n.targets))
            assert ast.literal_eval(node.value)==value
        old={'__name__':'frozen_gate'}
        exec(compile(z.read('agent/number_gate.py'),'frozen_gate','exec'),old)
    cases=['GMV 42，利润 71','2017年 2018-10-17T17:30:18','单次查询最多1000行，预览前20行',
           '下降5%，比率12:30','### 1. 报告\n金额1,000元','2017 全年 Q2，max_result_rows=1000']
    claims=[Claim(text='SQL value',value=42,evidence=[])]
    for text in cases:assert scan(text,claims,True)==old['scan'](text,claims,True)


@pytest.mark.parametrize('d,b,ok',[
    ([(6,8),(6,8)],[(8,10),(8,10)],True),
    ([(8,8),(5,8)],[(10,10),(10,10)],False),
    ([(8,8),(8,8)],[(10,10),(7,10)],False),
    ([(8,8)],[(10,10),(10,10)],False),
])
def test_adoption_requires_every_predeclared_threshold(d,b,ok):assert acceptance(d,b)==ok
