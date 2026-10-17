"""Execute every oracle on a read-only snapshot; publish no model performance."""

import hashlib
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg

from config import db_kwargs
from eval.dataset import QUESTION_FILE, execute_gold, load_questions
from scripts.common import record, start_log
from scripts.evidence import publish_log


def main():
    logger, path = start_log("validate_gold")
    failures = []
    with psycopg.connect(**db_kwargs(role="reader")) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        version = conn.execute("SELECT data_version FROM data_imports ORDER BY import_id DESC LIMIT 1").fetchone()[0]
        record(logger, "validation_started", data_version=version,
               question_file_sha256=hashlib.sha256(QUESTION_FILE.read_bytes()).hexdigest())
        questions = load_questions()
        for q in questions:
            try:
                with conn.transaction():
                    _, rows = execute_gold(conn, q)
                    record(logger, "gold_validated", question_id=q["id"], split=q["split"], rows=len(rows),
                        sql_sha256=hashlib.sha256(q["gold_sql"].encode()).hexdigest())
            except Exception as exc:
                failures.append(q["id"])
                record(logger, "gold_failed", question_id=q["id"], error=str(exc))
    record(logger, "validation_summary", total=len(questions), passed=len(questions)-len(failures), failures=failures)
    publish_log(path)
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
