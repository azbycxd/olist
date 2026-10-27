"""Execute an evaluation and append only measured results with durable receipts."""

import argparse
import hashlib
import json
import os
import re
import sys
from importlib.metadata import version as package_version
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from uuid import uuid4

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg
from psycopg.types.json import Jsonb

from config import EVAL_ADAPTER, EVAL_JUDGE, MODEL_TEMPERATURE, ROOT, SCHEMA_MODE, db_kwargs
from contracts import FinalAnswer
from eval.adapters import make_adapter, public_case
from eval.checker import DatabaseEvidence, check
from eval.dataset import QUESTION_FILE, execute_gold, load_questions
from eval.judge import ModelJudge
from eval.scoring import score
from scripts.common import record, start_log
from scripts.evidence import write_evidence
from mcp_olist.embedding_config import provenance

HEADER = """# 评测结果

仅由 `eval/run.py` 的真实运行追加。每行标注原始日志文件名，并链接 Git 跟踪的汇总证据。未运行或不可取得的指标留空。zero 是固定回答零的测试夹具，只验证评测链路，不代表模型能力；费用由实际用量与显式配置单价计算。

| 标签 | 类别 | 划分 | 正确题数 / 总题数 | 准确率 | D 关键事实命中率 | 无证据结论比例 | D 无证据数字比例 | D 归因评分 | 总 token | 费用 USD | 峰值上下文 token | 完成率 | 平均 token | 平均耗时 ms | BM25 recall@3 | 向量 recall@3 | 混合 recall@3 | 运行日志文件名 | 汇总证据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
"""


def ratio(numerator, denominator):
    return numerator/denominator if denominator else None


def summarize(rows):
    d_rows = [row for row in rows if row["category"] == "D"]
    grades = [row["judge"]["score"] for row in d_rows if row.get("judge")]
    return {"total": len(rows), "correct": sum(row["correct"] for row in rows),
        "completion_rate":ratio(sum(r.get("termination")=="final_answer" for r in rows),len(rows)),
        "peak_context_tokens":max((r.get("peak_context_tokens",0) for r in rows),default=0),
        "accuracy": ratio(sum(row["correct"] for row in rows), len(rows)),
        "fact_hits": sum(row["fact_hits"] or 0 for row in d_rows),
        "fact_total": sum(row["fact_total"] or 0 for row in d_rows),
        "fact_hit_rate": ratio(sum(row["fact_hits"] or 0 for row in d_rows), sum(row["fact_total"] or 0 for row in d_rows)),
        "unsupported_claims": sum(row["evidence"]["unsupported_claims"] for row in rows),
        "claim_count": sum(row["evidence"]["claim_count"] for row in rows),
        "unsupported_claim_ratio": ratio(sum(row["evidence"]["unsupported_claims"] for row in rows), sum(row["evidence"]["claim_count"] for row in rows)),
        "d_unsupported_numbers": sum(row["evidence"]["unsupported_numbers"] for row in d_rows),
        "d_number_count": sum(row["evidence"]["report_number_count"] for row in d_rows),
        "d_unsupported_number_ratio": ratio(sum(row["evidence"]["unsupported_numbers"] for row in d_rows), sum(row["evidence"]["report_number_count"] for row in d_rows)),
        "judge_mean": sum(grades)/len(grades) if grades else None, "judged_reports": len(grades),
        "average_latency_ms": sum(row["latency_ms"] for row in rows)/len(rows) if rows else None,
        "average_agent_latency_ms":sum(r["agent_latency_ms"] for r in rows)/len(rows) if rows and all('agent_latency_ms' in r for r in rows) else None,
        "failures": sum(bool(row.get("error")) for row in rows),
        "average_steps": sum(row.get("steps",0) for row in rows)/len(rows) if rows and all("steps" in r for r in rows) else None,
        "terminations": {reason:sum(r.get("termination") == reason for r in rows)
                         for reason in sorted({r["termination"] for r in rows if r.get("termination")})}}


def usage_summary(calls, input_price=None, output_price=None):
    if not calls:
        return {"model_calls": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": "0", "usage_complete": True}
    complete = all(c.get("usage") and all(isinstance(c["usage"].get(k), int) and c["usage"][k] >= 0
                   for k in ("prompt_tokens", "completion_tokens", "total_tokens")) for c in calls)
    counts = {"input_tokens": None, "output_tokens": None, "total_tokens": None}
    cost = None
    if complete:
        counts = {out: sum(c["usage"][key] for c in calls) for out,key in
            (("input_tokens", "prompt_tokens"), ("output_tokens", "completion_tokens"), ("total_tokens", "total_tokens"))}
        if input_price is not None and output_price is not None:
            cost = str((Decimal(counts["input_tokens"])*input_price + Decimal(counts["output_tokens"])*output_price)/Decimal(1000000))
    return {"model_calls": len(calls), **counts, "cost_usd": cost, "usage_complete": complete}


def percent(value):
    return "" if value is None else f"{value*100:.2f}%"


def append_results(summary, receipt, path=ROOT / "docs" / "RESULTS.md"):
    metrics, usage = summary["metrics"], summary["usage"]
    values = [summary["tag"], ",".join(summary["categories"]), summary["split"],
        f"{metrics['correct']} / {metrics['total']}", percent(metrics["accuracy"]), percent(metrics["fact_hit_rate"]),
        percent(metrics["unsupported_claim_ratio"]), percent(metrics["d_unsupported_number_ratio"]),
        "" if metrics["judge_mean"] is None else f"{metrics['judge_mean']:.3f}",
        "" if usage["total_tokens"] is None else str(usage["total_tokens"]), usage["cost_usd"] or "",
        str(metrics.get("peak_context_tokens","")),percent(metrics.get("completion_rate")),
        "" if metrics.get("average_tokens") is None else f"{metrics['average_tokens']:.2f}",
        "" if metrics.get("average_latency_ms") is None else f"{metrics['average_latency_ms']:.2f}", "", "", "",
        f"`{summary['source_log']}`", f"[{receipt.name}](../evidence/{receipt.name})"]
    if not path.exists():
        path.write_text(HEADER, encoding="utf-8")
    elif not path.read_text(encoding="utf-8").startswith(HEADER):
        raise ValueError("RESULTS.md header differs; preserve existing results and migrate it explicitly")
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write("| " + " | ".join(values) + " |\n")


def execute(args):
    os.environ["NUMBER_GATE"] = args.number_gate
    os.environ["SCHEMA_MODE"] = args.schema_mode
    os.environ["CONTEXT_STRATEGY"] = args.context_strategy
    os.environ["CONTEXT_SUMMARY_THRESHOLD"] = str(args.context_summary_threshold)
    os.environ["CONTEXT_LIMIT"] = str(args.context_limit)
    os.environ["RAG_MODE"] = args.rag_mode
    os.environ["USE_MEMORY"] = args.use_memory
    os.environ["AGENT_MODE"] = args.agent_mode
    os.environ["TOKEN_BUDGET"] = str(args.token_budget)
    selected = [q for q in load_questions() if q["category"] in args.categories and q["split"] == args.split]
    if getattr(args,"question_ids",None): selected=[q for q in selected if q["id"] in args.question_ids.split(",")]
    if not selected:
        raise ValueError("No matching questions")
    adapter = make_adapter(args.adapter)
    judge = ModelJudge() if args.judge == "model" else None
    prices = [os.getenv(name) for name in ("EVAL_INPUT_PRICE_PER_MILLION", "EVAL_OUTPUT_PRICE_PER_MILLION")]
    prices = [Decimal(p) if p else None for p in prices]
    if any(p is not None and (not p.is_finite() or p < 0) for p in prices):
        raise ValueError("Token prices must be nonnegative finite decimals")
    logger, log_path = start_log("eval_" + args.tag)
    results_path = ROOT / "docs" / "RESULTS.md"
    if results_path.exists() and not results_path.read_text(encoding="utf-8").startswith(HEADER):
        raise ValueError("RESULTS header mismatch; no evaluation was run")
    run_id = str(uuid4())
    calls, results = [], []
    log_finalized = False
    try:
        with psycopg.connect(**db_kwargs("agent", "app"), autocommit=True) as agent_db, \
                psycopg.connect(**db_kwargs(role="reader")) as oracle_db:
            if not agent_db.execute("SELECT pg_try_advisory_lock(730018)").fetchone()[0]:
                raise ValueError("Another evaluation is running; RESULTS append is serialized")
            oracle_db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            oracle_db.execute("SET LOCAL app.allowed_states = 'ALL'")
            data_version = oracle_db.execute("SELECT data_version FROM data_imports ORDER BY import_id DESC LIMIT 1").fetchone()[0]
            # Validate ALL selected gold queries before any adapter work or metrics.
            gold = {q["id"]: execute_gold(oracle_db, q)[0] for q in selected}
            embedding = provenance(used=args.adapter != 'zero' and args.rag_mode != 'off')
            record(logger, "run_started", run_id=run_id, tag=args.tag, adapter=adapter.name,
                adapter_version=adapter.version, judge=args.judge, split=args.split, categories=args.categories,
                data_version=data_version, temperature=MODEL_TEMPERATURE, schema_mode=args.schema_mode,
                embedding=embedding)
            for q in selected:
                # Private evaluator log only: never store the oracle in agent
                # query_results or pass it across the adapter boundary.
                record(logger, "oracle_result", question_id=q["id"], sql=q["gold_sql"], value=gold[q["id"]])
            for q in selected:
                username=f"eval-{getattr(args,'user_group',None) or run_id}-{q['id']}"
                user_id = agent_db.execute("INSERT INTO users(username,data_scope) VALUES(%s,ARRAY['ALL']) ON CONFLICT(username) DO UPDATE SET username=excluded.username RETURNING user_id", (username,)).fetchone()[0]
                setup_task = None
                if q.get("setup_turns"):
                    setup_task = agent_db.execute("INSERT INTO tasks (user_id,question,status) VALUES (%s,%s,'running') RETURNING task_id", (user_id, "\n".join(q["setup_turns"]))).fetchone()[0]
                task_id = agent_db.execute("INSERT INTO tasks (user_id,question,status) VALUES (%s,%s,'running') RETURNING task_id", (user_id, q["question"])).fetchone()[0]
                sequence = 0
                call_start=len(calls)

                def emit(kind, payload, tokens=0, latency_ms=0):
                    nonlocal sequence
                    sequence += 1
                    record(logger, kind, question_id=q["id"], task_id=str(task_id), payload=payload, tokens=tokens, latency_ms=latency_ms)
                    agent_db.execute("INSERT INTO events (task_id,seq,type,payload,tokens,latency_ms) VALUES (%s,%s,%s,%s,%s,%s)",
                        (task_id, sequence, kind, Jsonb(payload, dumps=lambda v: json.dumps(v, default=str)), tokens, latency_ms))
                    if kind == "plan":
                        row["plan"] = payload["plan"]
                        row["complex_route"] = not payload["simple_route"]
                    if kind == "tool_call" and payload.get("name")=="run_sql":
                        row["sql_calls"] = row.get("sql_calls",0)+1
                    if kind in {"finding_read","finding_reused","finding_written"}:
                        row.setdefault("finding_events",[]).append({"event":kind,"payload":payload})
                    if kind == "number_gate":
                        row.setdefault("number_gate_events",[]).append(payload)
                    if kind == "model_call":
                        calls.append(payload)
                    if kind == "termination":
                        row.update({"termination":payload["reason"], "steps":payload["steps"]})
                    if kind == "context_usage":
                        row["peak_context_tokens"] = max(row.get("peak_context_tokens",0),payload["prompt_tokens"])

                started = perf_counter()
                row = {"question_id": q["id"], "category": q["category"], "task_id": str(task_id),
                    "setup_task_id": str(setup_task) if setup_task else None, "user_id": str(user_id),
                    "judge": None, "judge_status": "off" if q["category"] == "D" else "not_applicable"}
                try:
                    response = FinalAnswer.model_validate(adapter.run(public_case(q, user_id, setup_task, task_id), emit))
                    row['agent_latency_ms']=(perf_counter()-started)*1000
                    audit = check(response, DatabaseEvidence(agent_db), str(task_id), data_version)
                    row.update(score(q, response, gold[q["id"]], audit))
                    row["evidence"] = audit
                    row["response"] = response.model_dump()
                    if row.get("termination") and row["termination"] != "final_answer":
                        row["error"] = row["termination"]
                    if q["category"] == "D" and judge:
                        try:
                            row["judge"] = judge.grade(q, response, gold[q["id"]], audit, emit)
                            row["judge_status"] = "scored"
                        except Exception as exc:
                            row["judge_status"] = "error"
                            row["judge_error"] = type(exc).__name__
                except Exception as exc:
                    row.update({"correct": False, "fact_hits": 0 if q["category"] == "D" else None,
                        "fact_total": len(q.get("required_facts", [])) or None, "fact_hit_rate": 0 if q["category"] == "D" else None,
                        "error": type(exc).__name__, "evidence": {"claims": [], "claim_count": 0,
                        "unsupported_claims": 0, "report_number_count": 0, "unsupported_numbers": 0,
                        "unsupported_claim_ratio": None, "unsupported_number_ratio": None}})
                row["agent_usage"] = usage_summary([c for c in calls[call_start:] if c.get("role")!="eval_judge"],*prices)
                row["latency_ms"] = (perf_counter()-started)*1000
                emit("eval_result", row, latency_ms=row["latency_ms"])
                for task in (task_id, setup_task):
                    if task:
                        agent_db.execute("UPDATE tasks SET status=%s,updated_at=now() WHERE task_id=%s", ("failed" if row.get("error") else "completed", task))
                results.append(row)
            summary = {"run_id": run_id, "tag": args.tag, "categories": args.categories, "split": args.split,
                "adapter": adapter.name, "adapter_version": adapter.version, "judge_mode": args.judge,
                "schema_mode":args.schema_mode,
                "context_strategy":args.context_strategy,"context_limit":args.context_limit,"context_summary_threshold":args.context_summary_threshold,
                "retrieval_method":os.getenv("RETRIEVAL_METHOD","vector"),
                "rag_mode":args.rag_mode,
                "use_memory":args.use_memory,
                "agent_mode":args.agent_mode,"number_gate":args.number_gate,"token_budget":args.token_budget,
                "boundary_guards":os.getenv('BOUNDARY_GUARDS','false'),
                "embedding":embedding,
                "temperature": MODEL_TEMPERATURE, "data_version": data_version,
                "question_file_sha256": hashlib.sha256(QUESTION_FILE.read_bytes()).hexdigest(),
                "runtime": {"python": sys.version.split()[0], **{p: package_version(p) for p in ("psycopg", "pydantic", "openai", "mcp", "sqlglot")}},
                "code_sha256": {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [ROOT/"contracts.py", ROOT/"config.py", ROOT/"scripts/runtime.py",
                        *sorted((ROOT/"eval").glob("*.py")), *sorted((ROOT/"agent").glob("*.py")),
                        *sorted((ROOT/"mcp_olist").glob("*.py"))]},
                "metrics": summarize(results), "by_category": {c: summarize([r for r in results if r["category"] == c]) for c in args.categories},
                "usage": usage_summary(calls, *prices), "pricing": {"input_per_million": prices[0], "output_per_million": prices[1]},
                "agent_usage":usage_summary([c for c in calls if c.get('role')!='eval_judge'],*prices),
                "model_calls": calls, "cases": results, "oracle_values": gold, "source_log": log_path.name,
                "human_calibration": "pending"}
            summary["metrics"]["average_tokens"] = (summary["usage"]["total_tokens"]/len(results)
                if summary["usage"]["total_tokens"] is not None and results else None)
            record(logger, "run_summary", **summary)
            log_finalized = True
            summary["source_log_sha256"] = hashlib.sha256(log_path.read_bytes()).hexdigest()
            receipt = write_evidence(log_path.stem + ".summary.json", summary)
            append_results(summary, receipt)
            print(f"Evidence: {receipt.name}")
            return summary
    except Exception as exc:
        if not log_finalized:
            record(logger, "run_failed", error=type(exc).__name__, detail=str(exc))
        raise


def recheck(path, tag):
    """Recheck recorded real responses; never call the model or edit old receipts."""
    original = json.loads(Path(path).read_text(encoding="utf-8"))
    if original["question_file_sha256"] != hashlib.sha256(QUESTION_FILE.read_bytes()).hexdigest():
        raise ValueError("Question file changed since the source run")
    logger, log_path = start_log("eval_"+tag)
    questions = {q["id"]:q for q in load_questions()}
    with psycopg.connect(**db_kwargs("agent","app"),autocommit=True) as db, psycopg.connect(**db_kwargs(role="reader")) as oracle:
        if not db.execute("SELECT pg_try_advisory_lock(730018)").fetchone()[0]: raise ValueError("Another evaluation is running")
        oracle.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        if oracle.execute("SELECT data_version FROM data_imports ORDER BY import_id DESC LIMIT 1").fetchone()[0] != original["data_version"]:
            raise ValueError("Data version changed")
        rows=[]
        for case in original["cases"]:
            row=dict(case)
            if "response" in case:
                response=FinalAnswer.model_validate(case["response"])
                q=questions[case["question_id"]]
                gold=execute_gold(oracle,q)[0]
                audit=check(response,DatabaseEvidence(db),case["task_id"],original["data_version"])
                row.update(score(q,response,gold,audit),evidence=audit)
            rows.append(row)
            record(logger,"rechecked_case",**row)
        summary={**original,"tag":tag,"run_id":str(uuid4()),"cases":rows,"metrics":summarize(rows),
            "by_category":{c:summarize([r for r in rows if r["category"]==c]) for c in original["categories"]},
            "source_receipt":Path(path).name,"source_receipt_sha256":hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "recheck_only":True,"new_model_calls":0,"usage_provenance":"Original real model run; no new model usage",
            "source_log":log_path.name,"recheck_scoring_sha256":hashlib.sha256((ROOT/"eval/scoring.py").read_bytes()).hexdigest()}
        summary['recheck_checker_sha256']=hashlib.sha256((ROOT/'eval/checker.py').read_bytes()).hexdigest()
        summary["metrics"]["average_tokens"]=original["metrics"].get("average_tokens")
        record(logger,"run_summary",**summary)
        summary["source_log_sha256"]=hashlib.sha256(log_path.read_bytes()).hexdigest()
        receipt=write_evidence(log_path.stem+".summary.json",summary)
        append_results(summary,receipt)
        print("Evidence:",receipt.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--step11-targeted',action='store_true',help='One fixed D dev twice + both boundary groups once; no further tuning')
    parser.add_argument('--boundary',action='store_true',help='Separate one-shot Step 10 behavioral suite; never appends holdout metrics')
    parser.add_argument('--step11-suite',action='store_true',help='One-shot original/new boundaries plus final CDE dev; never holdout')
    parser.add_argument('--step11-repair-dev',action='store_true',help='One retained correction pass after observed Step 11 regressions; dev only')
    parser.add_argument('--final-suite',choices=['dev','holdout'])
    parser.add_argument('--final-report',type=Path)
    parser.add_argument("--review-report",type=Path)
    parser.add_argument("--finding-reuse",action="store_true")
    parser.add_argument("--question-ids")
    parser.add_argument("--user-group")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--categories", default="A,B,C,D,E")
    parser.add_argument("--split", choices=["dev", "holdout"], default="dev")
    parser.add_argument("--adapter", default=EVAL_ADAPTER, choices=["zero", "single"])
    parser.add_argument("--schema-mode", default=SCHEMA_MODE, choices=["full", "on_demand"])
    parser.add_argument("--judge", default=EVAL_JUDGE, choices=["off", "model"])
    parser.add_argument("--context-strategy",default="none",choices=["none","mask","summary"])
    parser.add_argument("--review-suite",action="store_true")
    parser.add_argument("--context-summary-threshold",type=int,default=6000)
    parser.add_argument("--context-limit",type=int,default=16000)
    parser.add_argument("--recheck-evidence",type=Path)
    parser.add_argument("--rag-mode",default="off",choices=["off","inject","tool"])
    parser.add_argument("--retrieval",action="store_true")
    parser.add_argument("--embedding-benchmark",action="store_true")
    parser.add_argument("--use-memory",default="false",choices=["true","false"])
    parser.add_argument("--agent-mode",default="single",choices=["single","multi_no_review","multi"])
    parser.add_argument("--number-gate",default="false",choices=["true","false"])
    parser.add_argument("--token-budget",type=int,default=50000)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.tag):
        parser.error("tag must contain only ASCII letters, digits, underscores and hyphens")
    args.categories = sorted(set(args.categories.split(",")))
    if not args.categories or not set(args.categories) <= set("ABCDE"):
        parser.error("categories must be a comma-separated subset of A,B,C,D,E")
    if args.step11_targeted:
        from eval.step11_targeted import execute_suite
        execute_suite(execute)
    elif args.step11_repair_dev:
        from eval.step11_suite import repair_dev
        repair_dev(execute,recheck)
    elif args.step11_suite:
        from eval.step11_suite import execute_suite
        execute_suite(execute,recheck)
    elif args.boundary:
        from eval.boundary import execute as boundary
        boundary()
    elif args.final_suite:
        from eval.final_suite import execute_suite
        execute_suite(args,execute)
    elif args.final_report:
        from eval.final_suite import render
        render(args)
    elif args.review_report:
        from eval.review_report import execute as render
        render(args)
    elif args.finding_reuse:
        from eval.finding_reuse import execute_reuse
        execute_reuse(args,execute)
    elif args.review_suite:
        if args.split!="dev": parser.error("Review protocol is dev-only")
        from eval.review_suite import execute_suite
        execute_suite(args,execute,summarize)
    elif args.embedding_benchmark:
        from eval.embedding_benchmark import execute as benchmark
        benchmark(args)
    elif args.retrieval:
        from eval.retrieval import execute_retrieval
        execute_retrieval(args,HEADER)
    elif args.recheck_evidence: recheck(args.recheck_evidence,args.tag)
    else: execute(args)


if __name__ == "__main__":
    main()
