"""CLI task/event owner. The model subprocess receives no database credentials."""

import argparse
import json
import os
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

from config import FINAL_CONFIG, SCHEMA_MODE, db_kwargs
from scripts.common import record, start_log
from scripts.evidence import publish_log
from scripts.runtime import run_runtime


def main():
    for key,value in FINAL_CONFIG.items():os.environ.setdefault(key,value)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--schema-mode", choices=["full","on_demand"], default=SCHEMA_MODE)
    parser.add_argument('--username',default='default')
    parser.add_argument('--preference-only',action='store_true')
    args = parser.parse_args()
    os.environ["SCHEMA_MODE"] = args.schema_mode
    logger, path = start_log("ask")
    with psycopg.connect(**db_kwargs("agent","app"), autocommit=True) as conn:
        user = conn.execute("INSERT INTO users(username,data_scope) VALUES(%s,ARRAY['ALL']) ON CONFLICT(username) DO UPDATE SET username=excluded.username RETURNING user_id", (args.username,)).fetchone()[0]
        task = conn.execute("INSERT INTO tasks(user_id,question,status) VALUES(%s,%s,'running') RETURNING task_id",
                            (user,args.question)).fetchone()[0]
        sequence, termination = 0, None

        def emit(kind, payload, tokens=0, latency_ms=0):
            nonlocal sequence, termination
            sequence += 1
            if kind == "termination":
                termination = payload["reason"]
            record(logger, kind, task_id=str(task), payload=payload, tokens=tokens, latency_ms=latency_ms)
            conn.execute("INSERT INTO events(task_id,seq,type,payload,tokens,latency_ms) VALUES(%s,%s,%s,%s,%s,%s)",
                         (task,sequence,kind,Jsonb(payload),tokens,latency_ms))
        try:
            response = run_runtime(args.question, task, emit,preference_only=args.preference_only)
            if args.preference_only: termination='final_answer'
            record(logger, "answer", task_id=str(task), response=response.model_dump(), schema_mode=args.schema_mode)
            print(json.dumps(response.model_dump(),ensure_ascii=False,indent=2))
        finally:
            conn.execute("UPDATE tasks SET status=%s,updated_at=now() WHERE task_id=%s",
                         ("completed" if termination == "final_answer" else "failed",task))
            publish_log(path)
    return termination != "final_answer"


if __name__ == "__main__":
    raise SystemExit(main())
