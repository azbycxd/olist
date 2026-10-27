"""Actual loop trajectories for Step12 A2 (scripted model; no network)."""
import asyncio
from types import SimpleNamespace

from agent.loop import run_loop
from test_agent import Remote, completion


def trajectory(sqls, *, empty=False):
    class Results(Remote):
        async def call(self,name,arguments):
            if name=='run_sql' and empty:
                self.calls.append((name,arguments))
                return {'preview':[], 'row_count':0, 'result_id':str(len(self.calls))}
            return await super().call(name,arguments)
    remote, events = Results(), []
    responses = iter(completion([('run_sql',{'sql':sql})]) for sql in sqls)
    async def create(**kwargs): return next(responses)
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    result = asyncio.run(run_loop('fixture', remote, client, 'fixture', lambda *e:events.append(e), max_steps=len(sqls)))
    return result,events,remote


def test_alternating_signatures_stop_on_turn_six():
    outcome,events,remote=trajectory(['SELECT 1','SELECT 2']*3)
    assert outcome.termination=='no_progress' and outcome.steps==6
    assert len([x for x in remote.calls if x[0]=='run_sql'])==5
    assert any(e[0]=='no_progress' and e[1]['rule']=='alternating_window' for e in events)


def test_sql_case_and_whitespace_count_as_same_consecutive_call():
    outcome,events,remote=trajectory(['select count(*) from orders','SELECT COUNT(*)  FROM ORDERS','SELECT  count(*) FROM orders'])
    assert outcome.termination=='repeated_tool_calls'
    assert len([x for x in remote.calls if x[0]=='run_sql'])==2
    assert any(e[0]=='no_progress' and e[1]['rule']=='consecutive_repeat' for e in events)


def test_four_different_empty_state_queries_stop_after_result_four():
    outcome,events,_=trajectory([f"SELECT * FROM customers WHERE customer_state='{state}'" for state in ['SP','RJ','MG','BA','PR']],empty=True)
    assert outcome.termination=='no_progress' and outcome.steps==4
    assert any(e[0]=='no_progress' and e[1]['rule']=='empty_or_error' for e in events)


def test_normalization_preserves_quoted_identifiers_literals_and_bad_sql():
    from agent.sql_normalize import normalize_sql
    assert normalize_sql("select 'SP' as state") != normalize_sql("select 'sp' as state")
    assert normalize_sql('select "Order_ID" from orders') != normalize_sql('select "order_id" from orders')
    assert normalize_sql("select '")=="select '"


def test_nonempty_new_evidence_is_progress_and_mixed_success_resets():
    from agent.progress import Progress
    guard=Progress()
    for n in range(8): assert guard.after([{'row_count':1,'result_id':str(n)}]) is None
    for _ in range(3): assert guard.after([{'error':'timeout'}]) is None
    assert guard.after([{'error':'timeout'},{'preview':[{'n':1}]}]) is None
    for _ in range(3): assert guard.after([{'error':'timeout'}]) is None
    assert guard.after([{'error':'timeout'}])=='empty_or_error'


def test_empty_result_ids_do_not_reset_empty_streak():
    from agent.progress import Progress
    guard=Progress()
    for n in range(3): assert guard.after([{'row_count':0,'result_id':str(n)}]) is None
    assert guard.after([{'row_count':0,'result_id':'four'}])=='empty_or_error'
