from contextvars import ContextVar
from contextlib import contextmanager
from functools import wraps

# Set around Registry dispatch; inherited independently by concurrent asyncio tasks.
TOOL_CALL_ID = ContextVar('tool_call_id', default=None)
MCP_ROLE = ContextVar('mcp_role',default=None)


@contextmanager
def role_scope(role):
    token=MCP_ROLE.set(role)
    try:yield
    finally:MCP_ROLE.reset(token)


def role_bound(default):
    def decorate(function):
        @wraps(function)
        async def wrapped(*args,**kwargs):
            with role_scope(kwargs.get('role',default)):
                return await function(*args,**kwargs)
        return wrapped
    return decorate
