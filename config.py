"""Shared environment configuration; no model or agent mechanisms in Step 0."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", override=False)
DATA_DIR = ROOT / "data" / "raw"
LOG_DIR = ROOT / "logs"


def db_kwargs(database: str = "olist", role: str = "admin") -> dict:
    users = {"admin": os.getenv("PGUSER", "olist_admin"), "reader": "agent_ro", "app": "agent_app"}
    passwords = {
        "admin": os.getenv("POSTGRES_PASSWORD", "local_admin_change_me"),
        "reader": os.getenv("AGENT_RO_PASSWORD", "local_reader_change_me"),
        "app": os.getenv("AGENT_DB_PASSWORD", "local_agent_change_me"),
    }
    return {
        "host": os.getenv("PGHOST", "localhost"),
        "port": int(os.getenv("PGPORT", os.getenv("POSTGRES_PORT", "5432"))),
        "dbname": database,
        "user": users[role],
        "password": passwords[role],
        "connect_timeout": 10,
    }
