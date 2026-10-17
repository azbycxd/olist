"""JSON-lines subprocess protocol. No SQL credentials, driver or evaluation imports."""

import asyncio
import json
import os
import sys

from openai import AsyncOpenAI

from config import MCP_BEARER_TOKEN, MCP_URL, MODEL_TIMEOUT, OPENAI_BASE_URL, OPENAI_MODEL, SCHEMA_MODE
from agent.loop import run_loop
from agent.mcp_client import MCPClient


def emit(kind, payload, tokens=0, latency_ms=0):
    print(json.dumps({"event":kind, "payload":payload, "tokens":tokens, "latency_ms":latency_ms}, ensure_ascii=False), flush=True)


async def execute(request):
    if not OPENAI_MODEL or not os.getenv("OPENAI_API_KEY") or not MCP_BEARER_TOKEN:
        raise ValueError("OPENAI_MODEL, OPENAI_API_KEY and MCP_BEARER_TOKEN are required")
    async with AsyncOpenAI(base_url=OPENAI_BASE_URL, max_retries=0, timeout=MODEL_TIMEOUT) as client:
        async with MCPClient(MCP_URL, MCP_BEARER_TOKEN, request["task_id"]) as remote:
            outcome = await run_loop(request["question"], remote, client, OPENAI_MODEL, emit,
                                     schema_mode=SCHEMA_MODE)
    print(json.dumps({"response":outcome.response.model_dump(), "termination":outcome.termination,
                      "steps":outcome.steps, "total_tokens":outcome.total_tokens}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(execute(json.loads(sys.stdin.readline())))
    except Exception as exc:
        emit("runtime_error", {"error":type(exc).__name__})
        raise SystemExit(1)
