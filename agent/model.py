"""One logged model request, including explicit retries and actual usage."""

import asyncio
import json
import os
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from random import uniform
from time import perf_counter
from uuid import uuid4
import httpx
from openai import APIConnectionError, APITimeoutError
from agent.task_control import CONTROL,reservation_size,ModelStopped

from config import MODEL_EXTRA_BODY, MODEL_MAX_OUTPUT_TOKENS, MODEL_TEMPERATURE
from config import MODEL_RETRY_ATTEMPTS, MODEL_RETRY_BASE_SECONDS, MODEL_RETRY_CAP_SECONDS

@dataclass
class Budget:
    limit: int
    used: int=0
    complete: bool=True

ACTIVE_BUDGET=ContextVar('model_budget',default=None)


def classify_error(exc):
    status = getattr(exc, 'status_code', None)
    detail = (str(exc) + ' ' + json.dumps(getattr(exc, 'body', None), default=str)).lower()
    if status == 400 and any(s in detail for s in (
            'context_length_exceeded', 'maximum context length', 'context window',
            'context length', 'too many tokens', 'max_tokens exceeds', '上下文长度')):
        return 'context_limit'
    if status in {408,429,500,502,503,504} or isinstance(exc, (
            TimeoutError, ConnectionError, APIConnectionError, APITimeoutError,
            httpx.TimeoutException, httpx.NetworkError)):
        return 'retryable'
    if status in {400,401,403,404,422}:
        return 'fatal'
    return 'unknown'


def retry_delay(exc, attempt):
    value = getattr(getattr(exc, 'response', None), 'headers', {}).get('Retry-After')
    if value is not None:
        try:
            seconds = float(value)
        except (ValueError, TypeError):
            try:
                date = parsedate_to_datetime(value)
                if date.tzinfo is None: date = date.replace(tzinfo=timezone.utc)
                seconds = (date-datetime.now(timezone.utc)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                seconds = None
        if seconds is not None and seconds >= 0:
            return min(MODEL_RETRY_CAP_SECONDS, seconds)
    return uniform(0, min(MODEL_RETRY_CAP_SECONDS, MODEL_RETRY_BASE_SECONDS * 2**attempt))


async def request(client, model, messages, emit, *, role="agent", step=0, tools=None,
                  remaining=50000, sleep=asyncio.sleep, json_mode=False):
    wait_budget = float('inf')
    deadline = float('inf')
    for attempt in range(MODEL_RETRY_ATTEMPTS):
        budget=ACTIVE_BUDGET.get()
        if budget:
            remaining=min(remaining,budget.limit-budget.used)
            if remaining<=0:
                emit('budget_exhausted',{'role':role,'used':budget.used,'limit':budget.limit})
                return None
        payload = {"role":role,"step":step,"attempt":attempt,"requested_model":model,
            "temperature":MODEL_TEMPERATURE,"extra_body":MODEL_EXTRA_BODY,"usage":None,
            "error_class":None,
            "input_summary":{"messages":len(messages),"characters":sum(len(json.dumps(m,ensure_ascii=False)) for m in messages)}}
        output_limit=min(MODEL_MAX_OUTPUT_TOKENS,max(1,remaining))
        control=CONTROL.get()
        if control:
            call_id=str(uuid4())
            admission = await control({'call_id':call_id,'role':role,'step':step,'requested_model':model,
                           'reserved_tokens':reservation_size(messages,tools,output_limit)})
            payload['control_call_id']=call_id
            if admission and 'remaining_seconds' in admission:
                seconds = max(0.0, admission['remaining_seconds'])
                deadline = min(deadline, perf_counter()+seconds)
                wait_budget = min(wait_budget, seconds)
        start = perf_counter()
        completion = None
        error = None
        try:
            kwargs = {"tools":tools,"tool_choice":"auto"} if tools else {}
            if json_mode: kwargs["response_format"] = {"type":"json_object"}
            completion = await client.chat.completions.create(model=model,temperature=MODEL_TEMPERATURE,
                messages=messages,max_tokens=output_limit,
                **kwargs,**({"extra_body":MODEL_EXTRA_BODY} if MODEL_EXTRA_BODY else {}))
            payload.update(response_model=completion.model,
                system_fingerprint=getattr(completion,"system_fingerprint",None),
                usage=completion.usage.model_dump() if completion.usage else None,
                output_summary=completion.choices[0].message.model_dump(mode="json",exclude_none=True))
        except Exception as exc:
            error = exc
            detail = str(exc)
            for secret in (os.getenv("OPENAI_API_KEY"),os.getenv("MCP_BEARER_TOKEN")):
                if secret: detail = detail.replace(secret,"[redacted]")
            payload.update(error=type(exc).__name__,error_detail=detail[:1000],error_class=classify_error(exc))
        latency = (perf_counter()-start)*1000
        emit("model_call",payload,(payload.get("usage") or {}).get("total_tokens",0),latency)
        if error is not None and payload['error_class']=='retryable' and attempt < MODEL_RETRY_ATTEMPTS-1:
            delay = min(retry_delay(error, attempt), wait_budget, max(0.0, deadline-perf_counter()))
            if delay > 0:
                before = perf_counter()
                await sleep(delay)
                actual_wait_ms = (perf_counter()-before)*1000
                emit('model_retry_wait',{'role':role,'step':step,'attempt':attempt,
                     'control_call_id':payload.get('control_call_id'),'retry_wait_ms':actual_wait_ms})
                wait_budget = max(0.0, wait_budget-max(delay,actual_wait_ms/1000))
        if completion is not None:
            if budget and completion.usage: budget.used+=completion.usage.total_tokens
            elif budget: budget.complete=False
            return completion
        if payload['error_class'] in {'fatal','context_limit'}:
            raise ModelStopped('context_limit' if payload['error_class']=='context_limit' else 'model_fatal')
        if payload['error_class']!='retryable' or wait_budget <= 0 or perf_counter() >= deadline:
            return None
    return None
