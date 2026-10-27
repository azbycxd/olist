"""Shared environment configuration and explicit evaluation switches."""

import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
if os.getenv("OLIST_LOAD_DOTENV", "1") == "1":
    load_dotenv(ROOT / ".env", override=False)
# A complete explicit provider selection takes precedence over an unrelated
# ambient OPENAI_API_KEY. The runtime still uses the OpenAI-compatible SDK.
if os.getenv("DEEPSEEK_MODEL"):
    for suffix in ("API_KEY", "BASE_URL", "MODEL"):
        os.environ["OPENAI_"+suffix] = os.getenv("DEEPSEEK_"+suffix, "")
DATA_DIR = ROOT / "data" / "raw"
LOG_DIR = ROOT / "logs"
EVAL_ADAPTER = os.getenv("EVAL_ADAPTER", "zero")
EVAL_JUDGE = os.getenv("EVAL_JUDGE", "off")
MODEL_TEMPERATURE = 0
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL") or None
OPENAI_MODEL = os.getenv("OPENAI_MODEL") or None
MODEL_EXTRA_BODY = {"thinking":{"type":"disabled"}} if urlparse(OPENAI_BASE_URL or "").hostname == "api.deepseek.com" else {}
EVAL_JUDGE_MODEL = os.getenv("EVAL_JUDGE_MODEL") or OPENAI_MODEL
SCHEMA_MODE = os.getenv("SCHEMA_MODE", "on_demand")
MAX_STEPS = int(os.getenv("MAX_STEPS", "20"))
TOKEN_BUDGET = int(os.getenv("TOKEN_BUDGET", "50000"))
MODEL_TIMEOUT = float(os.getenv("MODEL_TIMEOUT", "60"))
MODEL_MAX_OUTPUT_TOKENS = int(os.getenv("MODEL_MAX_OUTPUT_TOKENS", "4096"))
MODEL_RETRY_ATTEMPTS = int(os.getenv("MODEL_RETRY_ATTEMPTS", "4"))
MODEL_RETRY_BASE_SECONDS = float(os.getenv("MODEL_RETRY_BASE_SECONDS", "1"))
MODEL_RETRY_CAP_SECONDS = float(os.getenv("MODEL_RETRY_CAP_SECONDS", "8"))
PROVIDER_FAILURE_THRESHOLD = int(os.getenv("PROVIDER_FAILURE_THRESHOLD", "5"))
PROVIDER_COOLDOWN_SECONDS = float(os.getenv("PROVIDER_COOLDOWN_SECONDS", "30"))
REPEATED_CALL_LIMIT = int(os.getenv("REPEATED_CALL_LIMIT", "3"))
NO_PROGRESS_WINDOW = int(os.getenv("NO_PROGRESS_WINDOW", "6"))
NO_PROGRESS_EMPTY_TURNS = int(os.getenv("NO_PROGRESS_EMPTY_TURNS", "4"))
if min(REPEATED_CALL_LIMIT,NO_PROGRESS_WINDOW,NO_PROGRESS_EMPTY_TURNS)<1:
    raise ValueError('Progress guard limits must be positive integers')
if MODEL_RETRY_ATTEMPTS < 1 or PROVIDER_FAILURE_THRESHOLD < 1 or min(
        MODEL_RETRY_BASE_SECONDS, MODEL_RETRY_CAP_SECONDS, PROVIDER_COOLDOWN_SECONDS) <= 0:
    raise ValueError("Retry and circuit settings must be positive")
MCP_URL = os.getenv("MCP_URL", "http://localhost:8001/mcp")
MCP_BEARER_TOKEN = os.getenv("MCP_BEARER_TOKEN", "")
CONTEXT_STRATEGY = os.getenv("CONTEXT_STRATEGY", "none")
CONTEXT_KEEP_TURNS = int(os.getenv("CONTEXT_KEEP_TURNS", "2"))
CONTEXT_SUMMARY_THRESHOLD = int(os.getenv("CONTEXT_SUMMARY_THRESHOLD", "6000"))
CONTEXT_LIMIT = int(os.getenv("CONTEXT_LIMIT", "16000"))

# Leave Step 9 behavior as default unless the fixed acceptance passes.
# Dimension checks are independent and remain enabled in both profiles.
def boundary_guards_enabled():
    return os.getenv('BOUNDARY_GUARDS','false').lower()=='true'


def dimension_precheck_enabled():
    return os.getenv('DIMENSION_PRECHECK','true').lower()=='true'

# Release defaults. Evaluations override each switch explicitly.
FINAL_CONFIG = {"AGENT_MODE": "single", "NUMBER_GATE": "true", "RAG_MODE": "inject",
    "RETRIEVAL_METHOD": "vector", "USE_MEMORY": "true", "CONTEXT_STRATEGY": "none",
    "CONTEXT_LIMIT": "16000", "CONTEXT_SUMMARY_THRESHOLD": "6000", "TOKEN_BUDGET": "100000",
    "BOUNDARY_GUARDS": str(boundary_guards_enabled()).lower()}


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
