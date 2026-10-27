"""Expose only typed transient infrastructure failures as retryable tool results."""
import asyncio
import inspect
from functools import wraps
import psycopg
from psycopg_pool import PoolTimeout


def retryable(exc):
    if isinstance(exc,(PoolTimeout,TimeoutError,ConnectionError)):return True
    state=getattr(exc,'sqlstate',None)
    if state and (state.startswith('08') or state in {'57014','57P01','57P02','57P03'}):return True
    return isinstance(exc,psycopg.OperationalError) and not state and not any(
        word in str(exc).lower() for word in ('authentication','permission','password'))


def infrastructure_errors(function):
    @wraps(function)
    async def wrapped(*args,**kwargs):
        try:
            return await function(*args,**kwargs) if inspect.iscoroutinefunction(function) else await asyncio.to_thread(function,*args,**kwargs)
        except Exception as exc:
            if not retryable(exc):raise
            return {'error':'infra_retryable','detail':'MCP database connection or request timeout; retry the task within its existing fault budget.'}
    return wrapped
