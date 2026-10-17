"""Database access is confined to the MCP service and offline evaluator."""

import json
from decimal import Decimal
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from config import db_kwargs
from mcp_olist.catalog import TABLES
from mcp_olist.sql_guard import MAX_ROWS, guard_sql


def json_value(value):
    # Preserve PostgreSQL numeric precision as strings across JSON and MCP.
    return json.loads(json.dumps(value, default=str, allow_nan=False))


def numeric_stats(rows, columns):
    stats = {}
    for name in columns:
        values = [Decimal(str(row[name])) for row in rows
                  if isinstance(row[name], (int, float, Decimal)) and not isinstance(row[name], bool)]
        values = [v for v in values if v.is_finite()]
        if values:
            stats[name] = {"min": min(values), "max": max(values), "mean": sum(values)/len(values)}
    return json_value(stats)


def describe(name):
    if name not in TABLES:
        raise ValueError("Unknown business table")
    with psycopg.connect(**db_kwargs(role="reader")) as conn:
        columns = conn.execute("""SELECT a.attname, format_type(a.atttypid,a.atttypmod),
            col_description(a.attrelid,a.attnum), a.attnotnull
            FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relname=%s AND a.attnum>0 AND NOT a.attisdropped
            ORDER BY a.attnum""", (name,)).fetchall()
        samples = conn.execute(sql.SQL("SELECT * FROM public.{} LIMIT 3").format(sql.Identifier(name))).fetchall()
    return {"name":name, "description":TABLES[name], "columns":[
        {"name":c[0], "type":c[1], "comment":c[2], "nullable":not c[3]} for c in columns],
        "samples":json_value([dict(zip([c[0] for c in columns], row)) for row in samples])}


def run_query(statement, task_id, lease_token=None):
    task_id = UUID(task_id)
    executable = guard_sql(statement)
    with psycopg.connect(**db_kwargs("agent", "app")) as agent_db:
        from mcp_olist.leases import validate
        validate(agent_db,task_id,lease_token)
        with psycopg.connect(**db_kwargs(role="reader")) as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            conn.execute("SET LOCAL statement_timeout = '10s'")
            conn.execute("SET LOCAL lock_timeout = '2s'")
            conn.execute("SET LOCAL search_path = pg_catalog, public")
            version = conn.execute("SELECT data_version FROM public.data_imports ORDER BY import_id DESC LIMIT 1").fetchone()[0]
            from mcp_olist.boundaries import validate_filters
            dimension_checks,missing=validate_filters(conn,executable)
            if missing:
                return {'error':'unknown_dimension','missing':missing,
                        'notice':'未找到该维度值，请核对名称或代码；尚未执行业务统计，不能将无记录解释为零。'}
            cursor = conn.execute(executable)
            columns = [c.name for c in cursor.description]
            if len(set(columns)) != len(columns):
                raise ValueError("Duplicate output columns; give each expression a unique SQL alias")
            raw = [dict(zip(columns, row)) for row in cursor.fetchmany(MAX_ROWS+1)]
            if len(raw) > MAX_ROWS:
                raise ValueError("Result exceeds enforced row limit")
            stats, rows = numeric_stats(raw, columns), json_value(raw)
            if len(json.dumps(rows, ensure_ascii=False).encode()) > 2_000_000:
                raise ValueError("Result exceeds 2 MB; select fewer columns or aggregate in SQL")
        validate(agent_db,task_id,lease_token,lock=True)
        result_id = agent_db.execute("""INSERT INTO query_results(task_id,sql,columns,rows,row_count,data_version)
            VALUES(%s,%s,%s,%s,%s,%s) RETURNING result_id""",
            (task_id, executable, Jsonb(columns), Jsonb(rows), len(rows), version)).fetchone()[0]
    return {"result_id":str(result_id), "sql":executable, "data_version":version, "row_count":len(rows),
            "dimension_checks":dimension_checks,
            "row_limit":MAX_ROWS, "columns":columns, "preview":rows[:20], "statistics":stats,
            "notice":"row_count and statistics describe the executed, capped query. Compute report numbers in SQL."}


def get_saved_result(result_id, task_id, offset=0, limit=20):
    if not isinstance(offset,int) or not isinstance(limit,int) or offset<0 or not 1<=limit<=1000:
        raise ValueError("offset must be nonnegative; limit must be 1..1000")
    with psycopg.connect(**db_kwargs("agent","app")) as conn:
        row = conn.execute("SELECT sql,columns,rows,row_count,data_version FROM query_results WHERE result_id=%s AND task_id=%s",
            (UUID(result_id),UUID(task_id))).fetchone()
    if not row: raise ValueError("Result is unavailable for this task")
    return {"result_id":str(result_id),"sql":row[0],"columns":row[1],"preview":row[2][offset:offset+limit],
            "row_count":row[3],"data_version":row[4],"offset":offset,"limit":limit}
