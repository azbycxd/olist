import ast
import json
import os
from collections import Counter
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from pydantic import ValidationError
from psycopg.types.json import Jsonb

from config import ROOT, db_kwargs
from contracts import FinalAnswer
from eval.adapters import ZeroAdapter, public_case
from eval.checker import DatabaseEvidence, check, report_numbers, supports
from eval.dataset import load_questions
from eval.generate_questions import generate
from eval.judge import ModelJudge
from eval.run import HEADER, append_results, summarize, usage_summary
from eval.scoring import gold_answer, score

REF = str(uuid4())


def answer(value=42, evidence=None, text="结果为 42", report=42):
    return FinalAnswer(answer=report, claims=[{"text": text, "value": value, "evidence": evidence or []}])


def audit(response, rows=None, task="task", version="v1"):
    return check(response, lambda ids: {REF: {"task_id": task, "data_version": version,
        "rows": rows if rows is not None else [{"n": 42}]}}, "task", "v1")


def test_questions_are_reproducible_and_stratified():
    actual = load_questions()
    assert actual == generate()
    assert Counter(q["category"] for q in actual) == {"A":10, "B":10, "C":25, "D":12, "E":10}
    assert Counter(q["split"] for q in actual) == {"dev":45, "holdout":22}
    assert all({q["split"] for q in actual if q["category"] == category} == {"dev", "holdout"} for category in "ABCDE")
    profile = (ROOT/"docs/data_profile.md").read_text(encoding="utf-8")
    assert all("## " + q["profile_section"] in profile for q in actual if q["category"] == "C")
    assert len({q["question"] for q in actual}) == len(actual)


def test_checker_rejects_fabricated_evidence():
    assert audit(answer())["unsupported_claim_ratio"] == 1
    response = answer(evidence=[REF])
    assert audit(response)["unsupported_claim_ratio"] == 0
    assert audit(response, rows=[{"n": 17}])["unsupported_claim_ratio"] == 1
    assert check(response, lambda _: {}, "task", "v1")["claims"][0]["reason"] == "missing_result"


@pytest.mark.parametrize("task,version,reason", [("another", "v1", "wrong_task"), ("task", "old", "stale_data_version")])
def test_evidence_is_scoped(task, version, reason):
    assert audit(answer(evidence=[REF]), task=task, version=version)["claims"][0]["reason"] == reason


def test_labeled_values_must_coexist_in_one_result_row():
    rows = [{"state":"SP", "gmv":100}, {"state":"RJ", "gmv":200}]
    assert supports({"state":"SP", "gmv":100}, rows)
    assert not supports({"state":"SP", "gmv":200}, rows)
    assert not supports({"profit":100}, rows)
    assert not supports([], rows)
    assert supports([], [])
    assert not supports(True, [{"n":1}])


def test_report_scanner_catches_unclaimed_numbers():
    checked = audit(answer(evidence=[REF], report="结果 42，另外利润 999。"))
    assert checked["unsupported_numbers"] == 1
    assert checked["report_number_count"] == 3
    assert report_numbers("2018 年 Q2，2018-04-01，收入 1.5 万元，增长 12.5%，1,234 个。") == [Decimal(15000),Decimal("12.5"),Decimal(1234)]
    assert check(FinalAnswer(answer="利润 999", claims=[]), lambda _: {}, "task", "v1")["unsupported_number_ratio"] == 1
    assert check(FinalAnswer(answer="无法回答", claims=[]), lambda _: {}, "task", "v1")["unsupported_claim_ratio"] is None


@pytest.mark.parametrize("value", [True, "答案100以及99", [100], "NaN"])
def test_number_scoring_does_not_search_for_gold_in_number_soup(value):
    assert not score({"answer_type":"number"}, answer(report=value), 100, {})["correct"]


def test_relative_error_boundary_and_zero():
    q={"answer_type":"number"}
    assert score(q, answer(report=101),100,{})["correct"]
    assert not score(q, answer(report=101.01),100,{})["correct"]
    assert score(q, answer(report=0),0,{})["correct"]
    assert not score(q, answer(report=0.001),0,{})["correct"]


def test_list_requires_exact_set():
    q={"answer_type":"list"}
    assert score(q,answer(report=["RJ","SP","SP"]),["SP","RJ"],{})["correct"]
    assert not score(q,answer(report=["RJ","SP","MG"]),["SP","RJ"],{})["correct"]


def test_key_fact_credit_requires_labels_and_rejects_contradictions():
    q={"answer_type":"key_facts"}
    response=answer(value={"gmv":100}, evidence=[REF], text="收入100", report="收入100")
    good=audit(response, rows=[{"gmv":100}])
    assert score(q,response,{"gmv":100},good)["correct"]
    assert score(q,answer(value=100),{"gmv":100},good)["fact_hits"] == 0
    response.claims.append(response.claims[0].model_copy(update={"value":{"gmv":999}}))
    assert score(q,response,{"gmv":100},good)["fact_hits"] == 0


def test_key_facts_still_require_a_nonempty_report():
    response=answer(value={"gmv":100},evidence=[REF],text="收入100",report=None)
    checked=audit(response,rows=[{"gmv":100}])
    assert score({"answer_type":"key_facts"},response,{"gmv":100},checked)["fact_hits"] == 1
    assert not score({"answer_type":"key_facts"},response,{"gmv":100},checked)["correct"]


def test_invalid_contract_and_gold_fail_explicitly():
    with pytest.raises(ValidationError):
        answer(evidence=["invented"])
    with pytest.raises((ValidationError, ValueError)):
        answer(value=float("nan"))
    with pytest.raises(ValueError):
        gold_answer({"answer_type":"number"},[{"value":None}])
    with pytest.raises(ValueError):
        gold_answer({"answer_type":"key_facts", "required_facts":["sales"]},[{"wrong":42}])


def test_public_adapter_boundary_and_preference_session():
    q=next(q for q in load_questions() if q["category"] == "E")
    case=public_case(q,"user","setup","followup")
    assert not hasattr(case,"gold_sql") and not hasattr(case,"split") and not hasattr(case,"template_id")
    events=[]
    result=ZeroAdapter().run(case,lambda *event: events.append(event))
    assert result.answer == 0
    assert [event[1]["phase"] for event in events] == ["preference_setup","new_session"]
    assert case.setup_task_id != case.task_id


def test_missing_model_usage_or_price_stays_unknown():
    assert usage_summary([])["cost_usd"] == "0"
    assert usage_summary([{"usage":None}])["total_tokens"] is None
    calls=[{"usage":{"prompt_tokens":10,"completion_tokens":5,"total_tokens":15}}]
    assert usage_summary(calls)["cost_usd"] is None
    assert usage_summary(calls,Decimal(1),Decimal(2))["cost_usd"] == "0.00002"


def test_judge_parameters_logging_and_invalid_grade():
    requests, events = [], []
    def create(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(model="test-model-version",system_fingerprint="test-fp",usage=None,
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"score":4,"rationale":"unit test"}'))])
    client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    grader=ModelJudge(client=client,model="test-model")
    grade=grader.grade({"question":"q","id":"test","rubric_focus":"scope"},answer(),{}, {},lambda *event:events.append(event))
    assert grade["score"] == 4 and requests[0]["temperature"] == 0
    assert requests[0]["response_format"] == {"type":"json_object"}
    assert events[0][1]["response_model"] == "test-model-version"
    assert events[0][1]["usage"] is None
    def bad_grade(**kwargs):
        return SimpleNamespace(model="test", usage=None, choices=[SimpleNamespace(message=SimpleNamespace(content='{"score":9,"rationale":"invalid"}'))])
    client.chat.completions.create = bad_grade
    with pytest.raises(ValidationError):
        grader.grade({"question":"q","id":"test","rubric_focus":"scope"},answer(),{}, {},lambda *event:events.append(event))
    assert events[-1][1]["error"] == "ValidationError"


def test_summary_uses_micro_denominators_and_preserves_unrun_judge(tmp_path):
    rows=[]
    for count, unsupported in [(1,1),(3,0)]:
        rows.append({"category":"D","correct":False,"fact_hits":0,"fact_total":2,
            "judge":None,"latency_ms":1,"evidence":{"claim_count":count,"unsupported_claims":unsupported,
            "report_number_count":count,"unsupported_numbers":unsupported}})
    metrics=summarize(rows)
    assert metrics["unsupported_claim_ratio"] == 0.25
    assert metrics["judge_mean"] is None
    summary={"tag":"unit","categories":["D"],"split":"dev","metrics":metrics,"usage":usage_summary([]),"source_log":"unit.jsonl"}
    destination=tmp_path/"results.md"
    receipt=tmp_path/"unit.summary.json"
    append_results(summary,receipt,destination)
    content=destination.read_text(encoding="utf-8")
    assert content.startswith(HEADER) and "25.00%" in content
    assert "../evidence/unit.summary.json" in content and "`unit.jsonl`" in content
    destination.write_text("existing user results",encoding="utf-8")
    with pytest.raises(ValueError,match="header differs"):
        append_results(summary,receipt,destination)
    assert destination.read_text(encoding="utf-8") == "existing user results"


def test_checker_does_not_import_agent_code():
    tree=ast.parse((ROOT/"eval/checker.py").read_text(encoding="utf-8"))
    imports=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    assert all(not name.startswith(("agent", "mcp_olist")) for name in imports if name)


@pytest.mark.integration
@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="requires Compose databases")
def test_checker_reads_real_query_results_table():
    conn=psycopg.connect(**db_kwargs("agent","app"))
    try:
        user=conn.execute("INSERT INTO users(username) VALUES(%s) RETURNING user_id",(f"checker-test-{uuid4()}",)).fetchone()[0]
        task=conn.execute("INSERT INTO tasks(user_id,question) VALUES(%s,'checker test') RETURNING task_id",(user,)).fetchone()[0]
        ref=conn.execute("INSERT INTO query_results(task_id,sql,rows,row_count,data_version) VALUES(%s,'SELECT 42 AS n',%s,1,'test') RETURNING result_id",(task,Jsonb([{"n":42}]))).fetchone()[0]
        verified=check(answer(evidence=[str(ref)]), DatabaseEvidence(conn),str(task),"test")
        assert verified["unsupported_claims"] == 0
        forged=check(answer(value=999,text="999",report=999,evidence=[str(ref)]),DatabaseEvidence(conn),str(task),"test")
        assert forged["unsupported_claims"] == 1
    finally:
        conn.rollback()
        conn.close()
