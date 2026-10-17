"""Launch the model runtime with an explicit credential/environment allowlist."""

import json
import os
import subprocess
import sys

from config import ROOT
from contracts import FinalAnswer

RUNTIME_ENV = set("""PATH SYSTEMROOT WINDIR TEMP TMP LANG LC_ALL SSL_CERT_FILE SSL_CERT_DIR
    HTTP_PROXY HTTPS_PROXY NO_PROXY OPENAI_API_KEY OPENAI_BASE_URL OPENAI_MODEL
    SCHEMA_MODE MAX_STEPS TOKEN_BUDGET MODEL_TIMEOUT MODEL_MAX_OUTPUT_TOKENS MCP_URL MCP_BEARER_TOKEN
    CONTEXT_STRATEGY CONTEXT_KEEP_TURNS CONTEXT_SUMMARY_THRESHOLD CONTEXT_LIMIT RAG_MODE""".split())


def runtime_environment():
    return {**{k:v for k,v in os.environ.items() if k in RUNTIME_ENV},
            "OLIST_LOAD_DOTENV":"0", "PYTHONUNBUFFERED":"1", "PYTHONIOENCODING":"utf-8"}


def run_runtime(question, task_id, emit):
    with subprocess.Popen([sys.executable, "-m", "agent.worker"], cwd=ROOT, env=runtime_environment(),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8") as process:
        try:
            process.stdin.write(json.dumps({"question":question, "task_id":str(task_id)}, ensure_ascii=False)+"\n")
            process.stdin.close()
            result = None
            for line in process.stdout:
                frame = json.loads(line)
                if "event" in frame:
                    emit(frame["event"], frame["payload"], frame["tokens"], frame["latency_ms"])
                elif "response" in frame:
                    result = frame
            if process.wait() or result is None:
                raise RuntimeError("Agent subprocess failed; inspect runtime_error/model_call events")
            return FinalAnswer.model_validate(result["response"])
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
