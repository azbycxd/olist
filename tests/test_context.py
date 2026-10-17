import asyncio

from agent.context import mask, pin, unpack
from agent.tools import Registry, untrusted
from test_agent import completion, run, FINAL, Remote


def test_mask_keeps_pairs_ids_recent_rows_and_notes():
    messages = [{"role":"system","content":"system"},{"role":"user","content":"question"}]
    for i in range(4):
        messages += [{"role":"assistant","tool_calls":[{"id":str(i)}]},
            {"role":"tool","tool_call_id":str(i),"content":untrusted({"result_id":str(i),"row_count":50,"preview":[{"x":i}]})}]
    assert mask(messages,2)==2
    assert unpack(messages[3]["content"])["result_id"] == "0"
    assert "preview" in unpack(messages[-1]["content"])
    assert [m.get("tool_call_id") for m in messages if m["role"]=="tool"] == ["0","1","2","3"]
    assert pin(messages,[{"text":"finding"}])[1]["role"] == "system"


def test_pressure_fails_on_observed_prompt_usage():
    outcome,_,events,_,_=run([completion([FINAL],tokens=50)],context_limit=40)
    assert outcome.termination=="context_limit"
    assert next(e[1]["prompt_tokens"] for e in events if e[0]=="context_usage")==49


def test_summary_is_logged_counted_and_keeps_valid_message_pairs():
    outcome,_,events,requests,_=run([completion([("run_sql",{"sql":"one"})]),completion([("run_sql",{"sql":"two"})]),
        completion(content="Earlier result IDs"),completion([FINAL])],context_strategy="summary",keep_turns=1,summary_threshold=5)
    assert outcome.termination=="final_answer" and outcome.total_tokens==40
    assert any(e[0]=="model_call" and e[1]["role"]=="context_summary" for e in events)
    assert requests[-1]["messages"][2]["role"]=="user"
