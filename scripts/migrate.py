"""Numbered, checksummed migrations, including safe recovery across databases."""

import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg

from config import ROOT, db_kwargs
from scripts.common import record, start_log

# This internal ledger is the only bootstrap DDL outside numbered migrations.
LEDGER = """CREATE TABLE IF NOT EXISTS schema_migrations (
    version integer PRIMARY KEY,
    filename text NOT NULL UNIQUE,
    checksum text NOT NULL,
    database_name text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp()
)"""


@dataclass(frozen=True)
class Migration:
    version: int
    filename: str
    checksum: str
    database: str
    sql: str

    @property
    def identity(self):
        return self.version, self.filename, self.checksum, self.database


def discover(directory: Path):
    migrations = []
    for path in sorted(directory.glob("*.sql")):
        match = re.fullmatch(r"(\d{3,})_[a-z0-9_]+\.sql", path.name)
        content = path.read_text(encoding="utf-8")
        target = re.match(r"-- database: (agent|olist)\n", content)
        if not match or not target:
            raise ValueError(f"Invalid migration filename or database header: {path.name}")
        migrations.append(Migration(int(match[1]), path.name, hashlib.sha256(path.read_bytes()).hexdigest(), target[1], content))
    migrations.sort(key=lambda m: m.version)
    if not migrations or [m.version for m in migrations] != list(range(1, len(migrations) + 1)):
        raise ValueError("Migration numbers must be unique and contiguous, starting at 001")
    return migrations


def verify_history(rows, migrations):
    known = {m.version: m.identity for m in migrations}
    for row in rows:
        if known.get(row[0]) != tuple(row[:4]):
            raise ValueError(f"Applied migration changed or disappeared: version {row[0]}")


def history(conn):
    return conn.execute("SELECT version, filename, checksum, database_name, applied_at FROM schema_migrations ORDER BY version").fetchall()


def apply_one(conn, migration):
    """DDL and its target-local receipt commit in the SAME transaction."""
    with conn.transaction():
        old = conn.execute("SELECT version, filename, checksum, database_name, applied_at FROM schema_migrations WHERE version=%s", (migration.version,)).fetchone()
        if old:
            verify_history([old], [migration])
            return old, False
        conn.execute(migration.sql)
        row = conn.execute("INSERT INTO schema_migrations (version, filename, checksum, database_name) VALUES (%s,%s,%s,%s) RETURNING version, filename, checksum, database_name, applied_at", migration.identity).fetchone()
        return row, True


def migrate(directory: Path = ROOT / "sql" / "migrations"):
    migrations = discover(directory)
    logger, log_path = start_log("migrate")
    with psycopg.connect(**db_kwargs("agent"), autocommit=True) as central:
        # All entry points use the central session lock; close also releases it.
        central.execute("SELECT pg_advisory_lock(730017)")
        central.execute(LEDGER)
        verify_history(history(central), migrations)
        with psycopg.connect(**db_kwargs("olist"), autocommit=True) as business:
            business.execute(LEDGER)
            local_rows = history(business)
            verify_history(local_rows, migrations)
            local_versions = {row[0] for row in local_rows}
            if any(row[3] == "olist" and row[0] not in local_versions for row in history(central)):
                raise ValueError("Central migration receipt exists but target receipt is missing; inspect the database restore")
            for migration in migrations:
                target = central if migration.database == "agent" else business
                row, applied = apply_one(target, migration)
                if target is business:
                    # If a crash occurs after the target commit, its durable receipt
                    # lets the next run repair this mirror without repeating DDL.
                    with central.transaction():
                        old = central.execute("SELECT version, filename, checksum, database_name, applied_at FROM schema_migrations WHERE version=%s", (migration.version,)).fetchone()
                        if old:
                            verify_history([old], [migration])
                        else:
                            central.execute("INSERT INTO schema_migrations (version, filename, checksum, database_name, applied_at) VALUES (%s,%s,%s,%s,%s)", row)
                record(logger, "migration_applied" if applied else "migration_verified", version=row[0], filename=row[1], checksum=row[2], database=row[3], applied_at=row[4])
    from scripts.evidence import publish_log
    publish_log(log_path)


if __name__ == "__main__":
    migrate()
