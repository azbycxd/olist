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

from config import EVAL_ADAPTER, EVAL_JUDGE, MODEL_TEMPERATURE, ROOT, db_kwargs
from contracts import FinalAnswer
from eval.adapters import make_adapter, public_case
from eval.checker import DatabaseEvidence, check
from eval.dataset import QUESTION_FILE, execute_gold, load_questions
from eval.judge import ModelJudge
from eval.scoring import score
from scripts.common import record, start_log
from scripts.evidence import write_evidence

HEADER = """# 评测结果

仅由 `eval/run.py` 的真实运行追加。每行标注原始日志文件名，并链接 Git 跟踪的汇总证据。未运行或不可取得的指标留空。zero 是固定回答零的测试夹具，只验证评测链路，不代表模型能力；费用由实际用量与显式配置单价计算。

| 标签 | 类别 | 划分 | 正确题数 / 总题数 | 准确率 | D 关键事实命中率 | 无证据结论比例 | D 无证据数字比例 | D 归因评分 | 总 token | 费用 USD | 运行日志文件名 | 汇总证据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
"""


def ratio(numerator, denominator):
    return numerator/denominator if denominator else None


def summarize(rows):
    d_rows = [row for row in rows if row["category"] == "D"]
    grades = [row["judge"]["score"] for row in d_rows if row.get("judge")]
    return {"total": len(rows), "correct": sum(row["correct"] for row in rows),
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
        "failures": sum(bool(row.get("error")) for row in rows)}


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
        f"`{summary['source_log']}`", f"[{receipt.name}](../evidence/{receipt.name})"]
    if not path.exists():
        path.write_text(HEADER, encoding="utf-8")
    elif not path.read_text(encoding="utf-8").startswith(HEADER):
        raise ValueError("RESULTS.md header differs; preserve existing results and migrate it explicitly")
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write("| " + " | ".join(values) + " |\n")


def execute(args):
    selected = [q for q in load_questions() if q["category"] in args.categories and q["split"] == args.split]
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
            data_version = oracle_db.execute("SELECT data_version FROM data_imports ORDER BY import_id DESC LIMIT 1").fetchone()[0]
            # Validate ALL selected gold queries before any adapter work or metrics.
            gold = {q["id"]: execute_gold(oracle_db, q)[0] for q in selected}
            record(logger, "run_started", run_id=run_id, tag=args.tag, adapter=adapter.name,
                adapter_version=adapter.version, judge=args.judge, split=args.split, categories=args.categories,
                data_version=data_version, temperature=MODEL_TEMPERATURE)
            for q in selected:
                # Private evaluator log only: never store the oracle in agent
                # query_results or pass it across the adapter boundary.
                record(logger, "oracle_result", question_id=q["id"], sql=q["gold_sql"], value=gold[q["id"]])
            for q in selected:
                user_id = agent_db.execute("INSERT INTO users (username) VALUES (%s) RETURNING user_id", (f"eval-{run_id}-{q['id']}",)).fetchone()[0]
                setup_task = None
                if q.get("setup_turns"):
                    setup_task = agent_db.execute("INSERT INTO tasks (user_id,question,status) VALUES (%s,%s,'running') RETURNING task_id", (user_id, "\n".join(q["setup_turns"]))).fetchone()[0]
                task_id = agent_db.execute("INSERT INTO tasks (user_id,question,status) VALUES (%s,%s,'running') RETURNING task_id", (user_id, q["question"])).fetchone()[0]
                sequence = 0

                def emit(kind, payload, tokens=0, latency_ms=0):
                    nonlocal sequence
                    sequence += 1
                    record(logger, kind, question_id=q["id"], task_id=str(task_id), payload=payload, tokens=tokens, latency_ms=latency_ms)
                    agent_db.execute("INSERT INTO events (task_id,seq,type,payload,tokens,latency_ms) VALUES (%s,%s,%s,%s,%s,%s)",
                        (task_id, sequence, kind, Jsonb(payload, dumps=lambda v: json.dumps(v, default=str)), tokens, latency_ms))
                    if kind == "model_call":
                        calls.append(payload)

                started = perf_counter()
                row = {"question_id": q["id"], "category": q["category"], "task_id": str(task_id),
                    "setup_task_id": str(setup_task) if setup_task else None, "user_id": str(user_id),
                    "judge": None, "judge_status": "off" if q["category"] == "D" else "not_applicable"}
                try:
                    response = FinalAnswer.model_validate(adapter.run(public_case(q, user_id, setup_task, task_id), emit))
                    audit = check(response, DatabaseEvidence(agent_db), str(task_id), data_version)
                    row.update(score(q, response, gold[q["id"]], audit))
                    row["evidence"] = audit
                    row["response"] = response.model_dump()
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
                row["latency_ms"] = (perf_counter()-started)*1000
                emit("eval_result", row, latency_ms=row["latency_ms"])
                for task in (task_id, setup_task):
                    if task:
                        agent_db.execute("UPDATE tasks SET status=%s,updated_at=now() WHERE task_id=%s", ("failed" if row.get("error") else "completed", task))
                results.append(row)
            summary = {"run_id": run_id, "tag": args.tag, "categories": args.categories, "split": args.split,
                "adapter": adapter.name, "adapter_version": adapter.version, "judge_mode": args.judge,
                "temperature": MODEL_TEMPERATURE, "data_version": data_version,
                "question_file_sha256": hashlib.sha256(QUESTION_FILE.read_bytes()).hexdigest(),
                "runtime": {"python": sys.version.split()[0], **{p: package_version(p) for p in ("psycopg", "pydantic", "openai")}},
                "code_sha256": {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [ROOT/"contracts.py", ROOT/"config.py", *sorted((ROOT/"eval").glob("*.py"))]},
                "metrics": summarize(results), "by_category": {c: summarize([r for r in results if r["category"] == c]) for c in args.categories},
                "usage": usage_summary(calls, *prices), "pricing": {"input_per_million": prices[0], "output_per_million": prices[1]},
                "model_calls": calls, "cases": results, "oracle_values": gold, "source_log": log_path.name,
                "human_calibration": "pending"}
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--categories", default="A,B,C,D,E")
    parser.add_argument("--split", choices=["dev", "holdout"], default="dev")
    parser.add_argument("--adapter", default=EVAL_ADAPTER, choices=["zero"])
    parser.add_argument("--judge", default=EVAL_JUDGE, choices=["off", "model"])
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.tag):
        parser.error("tag must contain only ASCII letters, digits, underscores and hyphens")
    args.categories = sorted(set(args.categories.split(",")))
    if not args.categories or not set(args.categories) <= set("ABCDE"):
        parser.error("categories must be a comma-separated subset of A,B,C,D,E")
    execute(args)


if __name__ == "__main__":
    main()
