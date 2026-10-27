"""Optional observed-ratio context estimate with one existing mask pass."""
import copy
import json
import math
import config
from agent.context import mask
from agent.task_control import ModelStopped


def estimated_prompt(messages):
    return math.ceil(sum(len(json.dumps(m,ensure_ascii=False)) for m in messages)*config.CONTEXT_TOKEN_COEFFICIENT)


def prepare(messages,output_limit,emit,role):
    if not config.CONTEXT_PREFLIGHT:return messages
    original=estimated_prompt(messages)
    final=original;changed=0
    if original+output_limit>config.CONTEXT_LIMIT:
        messages=copy.deepcopy(messages)
        changed=mask(messages,config.CONTEXT_KEEP_TURNS)
        final=estimated_prompt(messages)
    emit('context_preflight',{'role':role,'estimated_prompt_tokens_before':original,
        'estimated_prompt_tokens':final,'output_reserved_tokens':output_limit,
        'limit':config.CONTEXT_LIMIT,'masked_tool_results':changed})
    if final+output_limit>config.CONTEXT_LIMIT:raise ModelStopped('context_limit_preflight')
    return messages
