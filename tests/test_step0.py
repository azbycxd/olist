"""Acceptance checks against real PostgreSQL, with test writes rolled back."""

import os
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from config import db_kwargs
from scripts.load_olist import TABLES

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Set RUN_DB_TESTS=1 with Compose running")]


def test_two_databases_and_vector():
    with psycopg.connect(**db_kwargs(role="reader")) as conn:
        assert conn.execute("SELECT current_database()").fetchone()[0] == "olist"
        assert conn.execute("SHOW statement_timeout").fetchone()[0] == "10s"
        assert conn.execute("SHOW default_transaction_read_only").fetchone()[0] == "on"
    with psycopg.connect(**db_kwargs("agent", "app")) as conn:
        assert conn.execute("SELECT current_database()").fetchone()[0] == "agent"
        assert conn.execute("SELECT '[1,2,3]'::vector <-> '[1,2,3]'::vector").fetchone()[0] == 0


@pytest.mark.parametrize("statement", [
    "DELETE FROM orders WHERE false",
    "UPDATE orders SET order_status = 'test' WHERE false",
    "INSERT INTO orders SELECT * FROM orders WHERE false",
    "CREATE TABLE public.should_not_exist (id integer)",
    "CREATE TEMP TABLE should_not_exist (id integer)",
])
def test_reader_permissions_even_with_readonly_setting_disabled(statement):
    conn = psycopg.connect(**db_kwargs(role="reader"))
    try:
        # Demonstrate ACL enforcement, not just default_transaction_read_only.
        conn.execute("SET TRANSACTION READ WRITE")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(statement)
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.parametrize("database,role", [("olist", "app"), ("agent", "reader")])
def test_roles_cannot_connect_to_other_database(database, role):
    with pytest.raises(psycopg.OperationalError, match="permission denied for database"):
        psycopg.connect(**db_kwargs(database, role))


def test_source_rows_keys_and_timestamps():
    with psycopg.connect(**db_kwargs(role="reader")) as conn:
        manifest = conn.execute("SELECT manifest FROM data_imports ORDER BY import_id DESC LIMIT 1").fetchone()[0]
        for table in TABLES:
            count = conn.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))).fetchone()[0]
            assert count == manifest[table]["rows"]
        assert conn.execute("SELECT data_type FROM information_schema.columns WHERE table_name = 'orders' AND column_name = 'order_purchase_timestamp'").fetchone()[0] == "timestamp without time zone"
        assert conn.execute("SELECT count(*) FROM pg_constraint WHERE contype = 'f' AND connamespace = 'public'::regnamespace").fetchone()[0] == 6
        assert conn.execute("SELECT count(*) FROM pg_constraint WHERE contype = 'p' AND connamespace = 'public'::regnamespace").fetchone()[0] == len(TABLES) + 2


def test_core_tables_and_evidence_roundtrip():
    conn = psycopg.connect(**db_kwargs("agent", "app"))
    try:
        names = {r[0] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}
        assert names == {"users", "tasks", "events", "query_results", "memories", "schema_migrations"}
        user = conn.execute("INSERT INTO users (username) VALUES (%s) RETURNING user_id", (f"test-{uuid4()}",)).fetchone()[0]
        task = conn.execute("INSERT INTO tasks (user_id, question) VALUES (%s, 'test') RETURNING task_id", (user,)).fetchone()[0]
        conn.execute("INSERT INTO events (task_id, seq, type, payload, tokens, latency_ms) VALUES (%s, 1, 'tool_result', '{\"output_summary\":\"ok\"}', 0, 1.5)", (task,))
        result = conn.execute("INSERT INTO query_results (task_id, sql, rows, row_count, data_version) VALUES (%s, 'SELECT 42 AS n', '[{\"n\":42}]', 1, 'test') RETURNING result_id", (task,)).fetchone()[0]
        assert conn.execute("SELECT rows FROM query_results WHERE result_id = %s", (result,)).fetchone()[0] == [{"n": 42}]
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.parametrize("role", ["app", "admin"])
@pytest.mark.parametrize("statement", [
    "UPDATE events SET type = 'tampered' WHERE false",
    "DELETE FROM events WHERE false",
    "TRUNCATE events",
])
def test_events_are_append_only(role, statement):
    conn = psycopg.connect(**db_kwargs("agent", role))
    try:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(statement)
    finally:
        conn.rollback()
        conn.close()
