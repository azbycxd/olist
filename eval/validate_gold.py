"""Validate oracles and C trap strength on one read-only database snapshot."""

import hashlib
import sys
from decimal import Decimal
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg

from config import db_kwargs
from eval.checker import number
from eval.dataset import QUESTION_FILE, execute_gold, load_questions
from scripts.common import record, start_log
from scripts.evidence import publish_log


MIN_TRAP_DIFFERENCE = Decimal("0.01")


def compare_trap(gold, naive):
    gold, naive = number(gold), number(naive)
    if gold is None or naive is None:
        raise ValueError("Trap answers must be finite numbers")
    difference = abs(naive-gold)
    relative = difference/abs(gold) if gold else None
    reason = "zero_gold" if not gold else "difference_below_threshold" if relative < MIN_TRAP_DIFFERENCE else None
    return {"gold_value": gold, "naive_value": naive, "absolute_difference": difference,
            "relative_difference": relative, "minimum_relative_difference": MIN_TRAP_DIFFERENCE,
            "passed": reason is None, "reason": reason}


def main():
    logger, path = start_log("validate_gold")
    failures = []
    traps = []
    with psycopg.connect(**db_kwargs(role="reader")) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        version = conn.execute("SELECT data_version FROM data_imports ORDER BY import_id DESC LIMIT 1").fetchone()[0]
        record(logger, "validation_started", data_version=version,
               question_file_sha256=hashlib.sha256(QUESTION_FILE.read_bytes()).hexdigest(),
               validator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               minimum_trap_relative_difference=MIN_TRAP_DIFFERENCE)
        questions = load_questions()
        for q in questions:
            try:
                with conn.transaction():
                    gold, rows = execute_gold(conn, q)
                    if q["category"] == "C":
                        naive, _ = execute_gold(conn, {**q, "gold_sql": q["naive_sql"]})
                        comparison = compare_trap(gold, naive)
                        traps.append({"question_id": q["id"], **comparison})
                        record(logger, "trap_compared", question_id=q["id"], template_id=q["template_id"],
                               split=q["split"], parameters=q["parameters"],
                               gold_sql=q["gold_sql"], naive_sql=q["naive_sql"], **comparison)
                        if not comparison["passed"]:
                            raise ValueError(f"C trap must be replaced: {comparison['reason']}")
                    record(logger, "gold_validated", question_id=q["id"], split=q["split"], rows=len(rows),
                        sql_sha256=hashlib.sha256(q["gold_sql"].encode()).hexdigest())
            except Exception as exc:
                failures.append(q["id"])
                record(logger, "gold_failed", question_id=q["id"], error=str(exc))
    record(logger, "validation_summary", total=len(questions), passed=len(questions)-len(failures), failures=failures,
           c_total=sum(q["category"] == "C" for q in questions), c_compared=len(traps),
           c_passed=sum(t["passed"] for t in traps),
           c_rejected=[t["question_id"] for t in traps if not t["passed"]])
    publish_log(path)
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
