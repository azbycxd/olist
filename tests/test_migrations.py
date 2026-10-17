import os
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from config import ROOT, db_kwargs
from scripts import migrate as runner


def test_modified_or_missing_history_is_rejected(tmp_path):
    path = tmp_path / "001_test.sql"
    path.write_text("-- database: agent\nSELECT 1;", encoding="utf-8")
    original = runner.discover(tmp_path)
    path.write_text("-- database: agent\nSELECT 2;", encoding="utf-8")
    with pytest.raises(ValueError, match="changed or disappeared"):
        runner.verify_history([original[0].identity], runner.discover(tmp_path))
    with pytest.raises(ValueError, match="changed or disappeared"):
        runner.verify_history([original[0].identity], [])


def test_duplicate_or_missing_numbers_rejected(tmp_path):
    (tmp_path / "002_test.sql").write_text("-- database: agent\nSELECT 1;", encoding="utf-8")
    with pytest.raises(ValueError, match="contiguous"):
        runner.discover(tmp_path)


@pytest.mark.integration
@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="requires Compose databases")
def test_fresh_database_migrations_idempotence_and_recovery(monkeypatch, tmp_path):
    # Separate, uniquely named databases; never clear the user's business data.
    names = {name: f"test_migrations_{name}_{uuid4().hex}" for name in ("agent", "olist")}
    with psycopg.connect(**db_kwargs("postgres"), autocommit=True) as admin:
        created = []
        try:
            for name in names.values():
                admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
                created.append(name)
            monkeypatch.setattr(runner, "db_kwargs", lambda name: {**db_kwargs(name), "dbname": names[name]})
            # Avoid publishing ephemeral test migrations as real project evidence.
            monkeypatch.setattr("scripts.evidence.publish_log", lambda path: None)
            runner.migrate()
            with psycopg.connect(**runner.db_kwargs("agent")) as conn:
                before = runner.history(conn)
                assert len(before) == len(runner.discover(ROOT / "sql" / "migrations"))
                assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 0
            runner.migrate()
            with psycopg.connect(**runner.db_kwargs("agent")) as conn:
                assert runner.history(conn) == before
                conn.execute("DELETE FROM schema_migrations WHERE database_name = 'olist'")
            runner.migrate()  # repairs central mirror from the target-local receipt
            with psycopg.connect(**runner.db_kwargs("agent")) as conn:
                assert runner.history(conn) == before
                version = len(before)+1
                failed = runner.Migration(version, f"{version:03d}_failure.sql", "test", "agent",
                    "CREATE TABLE rollback_probe (id integer); SELECT 1/0;")
                with pytest.raises(psycopg.errors.DivisionByZero):
                    runner.apply_one(conn, failed)
                assert conn.execute("SELECT to_regclass('rollback_probe')").fetchone()[0] is None
                assert runner.history(conn) == before
        finally:
            for name in created:
                admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
