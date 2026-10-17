"""Credential-free admission handshake with the trusted parent worker."""
import asyncio
import json
import sys
from contextvars import ContextVar

CONTROL=ContextVar('task_control',default=None)


def reservation_size(messages,tools,max_output):
    # Conservative dispatch hold, NOT measured token usage. Byte serialization
    # plus framing headroom prevents concurrent calls spending the same quota.
    body=json.dumps({'messages':messages,'tools':tools},ensure_ascii=False).encode('utf-8')
    return len(body)+4096+128*len(messages)+max_output


class ParentControl:
    def __init__(self):self.lock=asyncio.Lock()
    async def __call__(self,payload):
        async with self.lock:
            print(json.dumps({'control':payload}),flush=True)
            line=await asyncio.to_thread(sys.stdin.readline)
            reply=json.loads(line) if line else {}
            if reply.get('call_id')!=payload['call_id'] or not reply.get('allowed'):
                raise RuntimeError('Task control denied further model work')
