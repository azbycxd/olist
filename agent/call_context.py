from contextvars import ContextVar

# Set around Registry dispatch; inherited independently by concurrent asyncio tasks.
TOOL_CALL_ID = ContextVar('tool_call_id', default=None)
