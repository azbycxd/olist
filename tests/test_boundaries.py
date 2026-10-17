import asyncio
from datetime import datetime,date
from decimal import Decimal
from types import SimpleNamespace
import pytest
from contracts import FinalAnswer,Claim
from agent.boundaries import context,make_assumption_explicit,date_ranges,prepare_context,CLARIFY
from agent.number_gate import scan
from eval.checker import report_numbers
from mcp_olist.boundaries import coverage,dimension_filters


@pytest.fixture(autouse=True)
def optional_profile(monkeypatch):monkeypatch.setenv('BOUNDARY_GUARDS','true')


def test_coverage_uses_observed_edges_without_claiming_complete_ingestion():
    c=coverage(datetime(2016,9,4,21,15,19),datetime(2018,10,17,17,30,18))
    assert c['partial_edge_months']==['2016-09','2018-10']
    assert c['calendar_years_fully_inside_observed_range']==[2017]
    assert '2018-10-17' in context('2018全年',{'coverage':c})
    assert not coverage(None,None)['available']
    with pytest.raises(RuntimeError):context('2025年',{'error':'unavailable'})


@pytest.mark.parametrize('sql,expected',[
    ("SELECT count(*) FROM customers c WHERE c.customer_state='XX'",[('customer_state','XX',None)]),
    ("SELECT sum(price) FROM products p WHERE LOWER(p.product_category_name) IN ('ghost','beds')",[('product_category_name','ghost','LOWER'),('product_category_name','beds','LOWER')]),
    ("SELECT * FROM orders WHERE 'canceled'=order_status",[('order_status','canceled',None)]),
    ("SELECT * FROM products WHERE product_category_name IS NULL OR product_category_name LIKE '%bed%'",[]),
    ("WITH x AS (SELECT 'unknown' AS customer_state) SELECT * FROM x WHERE x.customer_state='unknown'",[]),
])
def test_dimension_filter_extraction(sql,expected):assert dimension_filters(sql)==expected


@pytest.mark.parametrize('text',[
    '2016-09-04 21:15:19 至 2018-10-17T17:30:18.123+08:00',
    '2017年2月3日，2016–2018年，2017自然年，2018 Q2，时间 09:20',
    '单次查询最多 1,000 行；预览前 20 行；只返回前 1000 行；LIMIT 1000',
    '2017 全年，2017 为唯一完整日历年，1–3 月，10月17日，第2季度',
    'max_result_rows=1000；row_limit: 1000；preview_rows=20；前 1000 行；每片控制在 1000 行以内；前提是行数 ≤ 1000',
    '### 1. 日期范围\n### 2. 工具限制',
])
def test_gate_and_independent_checker_preserve_dates_and_tool_metadata(text):
    assert scan(text,[],True)==(text,[])
    assert report_numbers(text)==[]


@pytest.mark.parametrize('text,expected',[
    ('GMV 1000，客户 20',[1000,20]),('比率 12:30',[12,30]),
    ('单次查询最多 2000 行',[2000]),('日期 2017-01-02，利润 55',[55]),
])
def test_metadata_exemption_does_not_allow_business_numbers(text,expected):
    assert report_numbers(text)==[Decimal(n) for n in expected]
    assert len(scan(text,[],True)[1])==len(expected)


def test_missing_scope_never_invents_an_assumption_about_actual_sql():
    profile={'coverage':{'start_date':'2016-09-04','end_date':'2018-10-17'}}
    answer=FinalAnswer(answer=42,claims=[Claim(text='销售额',value=42,evidence=[])])
    assert '请指定时间范围' in make_assumption_explicit(answer,'销售额多少',profile).answer
    assert not answer.claims
    explicit=FinalAnswer(answer=42,claims=[Claim(text='假设沿用用户指定的 2017 年，销售额为 SQL 结果',value=42,evidence=[])])
    assert make_assumption_explicit(explicit,'销售额多少',profile).answer==42
    assert '2018-10-17' not in explicit.claims[0].text
    text=FinalAnswer(answer='销售额为 SQL 结果',claims=explicit.claims)
    assert '假设沿用用户指定的 2017 年' in make_assumption_explicit(text,'销售额多少',profile).answer
    scoped=FinalAnswer(answer=42,claims=[])
    assert make_assumption_explicit(scoped,'2017年销售额',profile)==scoped
    clarify=FinalAnswer(answer='请指定时间范围',claims=[])
    assert make_assumption_explicit(clarify,'GMV',profile).answer=='请指定时间范围'


def test_unknown_dimension_stops_before_model_can_turn_missing_into_zero():
    from test_agent import Remote,completion
    from agent.loop import run_loop
    class Missing(Remote):
        async def call(self,name,args):
            if name=='run_sql':return {'error':'unknown_dimension','missing':[{'dimension':'customer_state','value':'XX'}]}
            return await super().call(name,args)
    calls=[]
    async def create(**kw):
        calls.append(kw)
        return completion([('run_sql',{'sql':"SELECT count(*) FROM customers WHERE customer_state='XX'"})])
    client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    result=asyncio.run(run_loop('XX 州多少客户',Missing(),client,'test',lambda *a:None))
    assert len(calls)==1 and '未找到该值' in result.response.answer and '请核对' in result.response.answer
