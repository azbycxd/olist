"""Shared environment configuration and explicit evaluation switches."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", override=False)
DATA_DIR = ROOT / "data" / "raw"
LOG_DIR = ROOT / "logs"
EVAL_ADAPTER = os.getenv("EVAL_ADAPTER", "zero")
EVAL_JUDGE = os.getenv("EVAL_JUDGE", "off")
MODEL_TEMPERATURE = 0
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL") or None
OPENAI_MODEL = os.getenv("OPENAI_MODEL") or None
EVAL_JUDGE_MODEL = os.getenv("EVAL_JUDGE_MODEL") or OPENAI_MODEL


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
