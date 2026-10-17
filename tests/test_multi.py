import asyncio
import os
from uuid import uuid4
from types import SimpleNamespace

import psycopg
import pytest
from pydantic import ValidationError
from contracts import Claim
from agent.state import Plan,Part
from agent.multi import schedule
from agent.review import value_in_rows,review
from agent.writer import mark_numbers
from agent.retrieval import ToolView
from eval.checker import report_numbers
from config import db_kwargs
from mcp_olist.blackboard import read_state,write_state


def test_plan_rejects_cycles_and_unknown_dependencies():
    assert Part(id='declining_count_and_largest_drop',question='q').id
    with pytest.raises(ValueError):Part(id='a'*65,question='q')
    for parts in [[{'id':'a','question':'q','depends_on':['a']}],
        [{'id':'a','question':'q','depends_on':['b']},{'id':'b','question':'q','depends_on':['a']}],
        [{'id':'a','question':'q','depends_on':['missing']}]]:
        with pytest.raises(ValueError):Plan(subtasks=parts)


def test_scheduler_parallelism_and_dependency_order():
    plan=Plan(subtasks=[Part(id='a',question='a'),Part(id='b',question='b'),Part(id='c',question='c',depends_on=['a','b'])])
    running=set();done=set();peaks=[]
    async def job(part):
        assert set(part.depends_on)<=done
        running.add(part.id);peaks.append(len(running))
        await asyncio.sleep(0.01)
        running.remove(part.id);done.add(part.id)
    asyncio.run(schedule(plan,job))
    assert max(peaks)==2 and done=={'a','b','c'}


def test_review_binds_columns_to_one_row_and_rejects_sign_forgery():
    rows=[{'state':'SP','amount':'42.0'},{'state':'RJ','amount':'7.0'}]
    assert value_in_rows([{'state':'SP','amount':42}],rows)
    assert not value_in_rows({'state':'SP','amount':7},rows)
    assert not value_in_rows(-42,rows)


def test_missing_evidence_never_reaches_semantic_approval():
    class Remote:
        async def call(self,*args):return {'error':'mcp_tool_error'}
    claims=[Claim(text='invented',value=42,evidence=[str(uuid4())])]
    result=asyncio.run(review('question',claims,Remote(),None,'unused',lambda *args:None))
    assert not result[0].approved


def test_report_marks_new_numbers_but_not_direction_or_citation_identifiers():
    ident='12345678-1234-1234-1234-123456789012'
    claims=[Claim(text='decline',value={'change_pct':-5},evidence=[ident])]
    report,n=mark_numbers(f'下降 5%；另一个未经验证金额 999。[证据](#result-{ident})',claims)
    assert n==1 and '>999' in report and '下降 5%' in report
    assert report_numbers(f'下降 5% [证据](#result-{ident})')==[5]
    assert report_numbers('2018-Q1 销售额 2018')==[2018]
    assert mark_numbers('2018-Q1 下降 5%',claims)[1]==0


def test_control_tools_are_hidden_from_all_language_model_modes():
    remote=SimpleNamespace(tools=[{'function':{'name':n}} for n in ('state_read','state_write','run_sql')])
    assert [t['function']['name'] for t in ToolView(remote).tools]==['run_sql']


def test_rejected_subtasks_are_retried_once_then_dropped(monkeypatch):
    from agent import multi
    from agent.state import Board,Subtask,Decision
    from agent.loop import Outcome
    from contracts import FinalAnswer
    plan=Plan(subtasks=[Part(id='a',question='first'),Part(id='b',question='second')])
    state=Board(plan=plan,subtasks={p.id:Subtask(question=p.question,depends_on=[]) for p in plan.subtasks})
    runs=[]
    async def control(remote,name,args):
        if name=='state_read':return state
        data=args['payload'];role=args['role']
        if role=='analyst':
            part=state.subtasks[data['id']]
            state.subtasks[data['id']]=Subtask.model_validate({**part.model_dump(),**{k:v for k,v in data.items() if k!='id'}})
        elif role=='reviewer':
            part=state.subtasks[data['id']];part.review=[Decision(**d) for d in data['decisions']];part.status='unverified'
        elif role=='writer':state.report=FinalAnswer.model_validate(data)
        return state
    async def planner(*args,**kwargs):return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=plan.model_dump_json()))])
    async def prepare(remote,*args):return remote,''
    async def analyze(question,*args,**kwargs):
        runs.append(question)
        return Outcome(FinalAnswer(answer=42,claims=[{'text':'bad','value':42,'evidence':[]}]),'final_answer',1,10)
    async def reject(*args,**kwargs):return [Decision(claim_index=0,approved=False,reason='unsupported')]
    monkeypatch.setattr(multi,'control',control);monkeypatch.setattr(multi,'request',planner)
    monkeypatch.setattr(multi,'prepare',prepare);monkeypatch.setattr(multi,'run_loop',analyze);monkeypatch.setattr(multi,'review',reject)
    result=asyncio.run(multi.run_multi('question',None,None,'test',lambda *args:None,mode='multi',rag_mode='off',schema_mode='on_demand'))
    assert runs.count('first')==runs.count('second')==2 and result.response.claims==[]
    assert all(p.attempt==1 for p in state.subtasks.values())


@pytest.mark.integration
@pytest.mark.skipif(os.getenv('RUN_DB_TESTS')!='1',reason='requires database')
def test_persistent_role_boundaries_and_writer_rejection():
    with psycopg.connect(**db_kwargs('agent','app'),autocommit=True) as conn:
        user=conn.execute('INSERT INTO users(username) VALUES(%s) RETURNING user_id',('board-'+str(uuid4()),)).fetchone()[0]
        task=str(conn.execute("INSERT INTO tasks(user_id,question,status) VALUES(%s,'test','running') RETURNING task_id",(user,)).fetchone()[0])
        plan={'subtasks':[{'id':'a','question':'q','depends_on':[]}]}
        write_state(task,'planner',plan)
        assert read_state(task)['plan']==plan
        with pytest.raises(ValueError):write_state(task,'analyst',{'id':'a','review':[]})
        claim={'text':'fact','value':42,'evidence':[str(uuid4())]}
        write_state(task,'analyst',{'id':'a','status':'completed','claims':[claim]})
        write_state(task,'reviewer',{'id':'a','decisions':[{'claim_index':0,'approved':False,'reason':'unverified'}]})
        with pytest.raises(ValueError):write_state(task,'writer',{'answer':'bad','claims':[claim]})
        write_state(task,'writer',{'answer':'未能验证','claims':[]})
        assert read_state(task)['report']['claims']==[]
        with pytest.raises(ValueError):read_state(str(uuid4()))
def test_writer_accepts_only_answer_and_inert_format_echo():
    from agent.writer import parse_answer
    assert parse_answer('{"answer":"text","type":"json_object"}')=='text'
    assert parse_answer('{"answer":"text"}')=='text'
    with pytest.raises(ValueError):parse_answer('{"answer":"text","claims":[]}')
    with pytest.raises(ValueError):parse_answer('{"answer":"text","type":"other"}')

