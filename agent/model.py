"""One logged model request, including explicit retries and actual usage."""

import asyncio
import json
import os
from contextvars import ContextVar
from dataclasses import dataclass
from time import perf_counter

from config import MODEL_EXTRA_BODY, MODEL_MAX_OUTPUT_TOKENS, MODEL_TEMPERATURE

@dataclass
class Budget:
    limit: int
    used: int=0
    complete: bool=True

ACTIVE_BUDGET=ContextVar('model_budget',default=None)


async def request(client, model, messages, emit, *, role="agent", step=0, tools=None,
                  remaining=50000, sleep=asyncio.sleep, json_mode=False):
    for attempt in range(4):
        budget=ACTIVE_BUDGET.get()
        if budget:
            remaining=min(remaining,budget.limit-budget.used)
            if remaining<=0:
                emit('budget_exhausted',{'role':role,'used':budget.used,'limit':budget.limit})
                return None
        payload = {"role":role,"step":step,"attempt":attempt,"requested_model":model,
            "temperature":MODEL_TEMPERATURE,"extra_body":MODEL_EXTRA_BODY,"usage":None,
            "input_summary":{"messages":len(messages),"characters":sum(len(json.dumps(m,ensure_ascii=False)) for m in messages)}}
        start = perf_counter()
        completion = None
        try:
            kwargs = {"tools":tools,"tool_choice":"auto"} if tools else {}
            if json_mode: kwargs["response_format"] = {"type":"json_object"}
            completion = await client.chat.completions.create(model=model,temperature=MODEL_TEMPERATURE,
                messages=messages,max_tokens=min(MODEL_MAX_OUTPUT_TOKENS,max(1,remaining)),
                **kwargs,**({"extra_body":MODEL_EXTRA_BODY} if MODEL_EXTRA_BODY else {}))
            payload.update(response_model=completion.model,
                system_fingerprint=getattr(completion,"system_fingerprint",None),
                usage=completion.usage.model_dump() if completion.usage else None,
                output_summary=completion.choices[0].message.model_dump(mode="json",exclude_none=True))
        except Exception as exc:
            detail = str(exc)
            for secret in (os.getenv("OPENAI_API_KEY"),os.getenv("MCP_BEARER_TOKEN")):
                if secret: detail = detail.replace(secret,"[redacted]")
            payload.update(error=type(exc).__name__,error_detail=detail[:1000])
        emit("model_call",payload,(payload.get("usage") or {}).get("total_tokens",0),(perf_counter()-start)*1000)
        if completion is not None:
            if budget and completion.usage: budget.used+=completion.usage.total_tokens
            elif budget: budget.complete=False
            return completion
        if attempt < 3: await sleep(2**attempt)
    return None
