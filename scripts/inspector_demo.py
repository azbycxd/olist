"""Prepare a task for the official Inspector and retain its real CLI response."""

import argparse
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

import psycopg

from config import LOG_DIR, MCP_BEARER_TOKEN, db_kwargs
from scripts.common import record, start_log
from scripts.evidence import publish_log


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "verify"])
    parser.add_argument("--response", type=Path, default=LOG_DIR/"inspector_call.json")
    args = parser.parse_args()
    config_file = LOG_DIR/"inspector.private.json"
    with psycopg.connect(**db_kwargs("agent", "app")) as db:
        if args.action == "prepare":
            if len(MCP_BEARER_TOKEN) < 24:
                raise ValueError("Configure MCP_BEARER_TOKEN first")
            user = db.execute("INSERT INTO users(username,data_scope) VALUES(%s,ARRAY['ALL']) RETURNING user_id",
                              ("inspector-"+uuid4().hex,)).fetchone()[0]
            task = db.execute("INSERT INTO tasks (user_id,question,status) VALUES (%s,%s,'running') RETURNING task_id",
                              (user,"Official MCP Inspector: SELECT COUNT(*) AS orders FROM orders")).fetchone()[0]
            config_file.write_text(json.dumps({"mcpServers":{"olist":{
                "type":"streamable-http", "url":"http://localhost:8001/mcp",
                "headers":{"Authorization":"Bearer "+MCP_BEARER_TOKEN,"X-Task-ID":str(task)}
            }}},indent=2),encoding="utf-8")
            print("Prepared Inspector task", task, "(private config in ignored logs/)")
            return
        config = json.loads(config_file.read_text(encoding="utf-8"))["mcpServers"]["olist"]
        response = json.loads(args.response.read_text(encoding="utf-8-sig"))
        if response.get("isError"):
            raise ValueError("Inspector call returned an MCP error")
        result = response.get("structuredContent") or json.loads(response["content"][0]["text"])
        task = UUID(config["headers"]["X-Task-ID"])
        saved = db.execute("SELECT sql,rows,row_count,data_version FROM query_results WHERE result_id=%s AND task_id=%s",
                           (UUID(result["result_id"]),task)).fetchone()
        if not saved or saved[2] != result["row_count"] or saved[1] != result["preview"]:
            raise ValueError("Inspector response does not match persisted evidence")
        db.execute("UPDATE tasks SET status='completed',updated_at=now() WHERE task_id=%s",(task,))
        logger,path = start_log("inspector")
        record(logger,"inspector_verified",client="@modelcontextprotocol/inspector",client_version="1.0.2",
               transport="Streamable HTTP",method="tools/call",tool="run_sql",task_id=str(task),
               response_log=args.response.name,response_sha256=hashlib.sha256(args.response.read_bytes()).hexdigest(),
               result=result,persisted_sql=saved[0],data_version=saved[3])
        print("Evidence:",publish_log(path).name)


if __name__ == "__main__":
    main()
