import json
from pathlib import Path

from eval.scoring import gold_answer

QUESTION_FILE = Path(__file__).with_name("questions.jsonl")


def load_questions(path=QUESTION_FILE):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = set()
    for q in rows:
        if not {"id", "category", "question", "gold_sql", "answer_type", "split"} <= q.keys():
            raise ValueError("Missing required question field")
        if q["id"] in ids or q["category"] not in "ABCDE" or q["split"] not in {"dev", "holdout"}:
            raise ValueError(f"Invalid question identity or split: {q['id']}")
        if q["answer_type"] not in {"number", "list", "key_facts"}:
            raise ValueError("Invalid answer_type")
        if q["category"] in "CE" and not q.get("template_id"):
            raise ValueError("Parameterized cases require template_id")
        if q["category"] == "C" and (q["answer_type"] != "number" or not isinstance(q.get("naive_sql"), str)
                                      or not q["naive_sql"].strip()):
            raise ValueError("C cases require numeric answers and a nonempty naive_sql")
        if q["category"] == "E" and (not q.get("setup_turns") or not q.get("new_session")):
            raise ValueError("Memory cases require setup turns followed by a new session")
        ids.add(q["id"])
    return rows


def execute_gold(conn, question):
    cursor = conn.execute(question["gold_sql"])
    columns = [column.name for column in cursor.description]
    if len(columns) != len(set(columns)):
        raise ValueError("Gold SQL has duplicate result column names")
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    return gold_answer(question, rows), rows
