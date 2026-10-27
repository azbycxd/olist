"""Process-local, lazy pools. Credentials never cross into agent subprocesses."""
import atexit
import os
import threading
from contextlib import contextmanager
from contextvars import ContextVar

from psycopg_pool import ConnectionPool, PoolTimeout
import config

_pools = {}
_lock = threading.Lock()
request_state = ContextVar('pool_request_state', default=None)


def validate_settings(component):
    required = ['AGENT_DB_PASSWORD']
    if component in {'mcp', 'worker'}:
        required += ['AGENT_RO_PASSWORD', 'MCP_BEARER_TOKEN']
    if component == 'api':
        required += ['MEMORY_API_SECRET']
    if component == 'worker':
        required += ['OPENAI_API_KEY', 'OPENAI_MODEL']
    missing = [key for key in required if not os.getenv(key, '').strip()]
    if missing:
        raise ValueError('Missing required settings: ' + ', '.join(missing))
    if component == 'api' and len(os.environ['MEMORY_API_SECRET']) < 32:
        raise ValueError('MEMORY_API_SECRET must contain at least 32 characters')
    if component in {'worker', 'mcp'} and len(os.environ['MCP_BEARER_TOKEN']) < 24:
        raise ValueError('MCP_BEARER_TOKEN must contain at least 24 characters')


def pool(component, database='agent', role='app'):
    allowed = {('api', 'agent', 'app'): config.API_POOL_MAX,
               ('mcp', 'agent', 'app'): config.MCP_AGENT_POOL_MAX,
               ('mcp', 'olist', 'reader'): config.MCP_OLIST_POOL_MAX,
               ('worker', 'agent', 'app'): config.WORKER_AGENT_POOL_MAX,
               ('worker', 'olist', 'reader'): config.WORKER_OLIST_POOL_MAX}
    key = (component, database, role)
    maximum = allowed[key]  # Reject accidental privileged roles / extra pools.
    with _lock:
        if key not in _pools:
            _pools[key] = ConnectionPool(
                kwargs={**config.db_kwargs(database, role),
                        'application_name': f'olist:{component}:{database}:{os.getpid()}'},
                min_size=0, max_size=maximum, timeout=config.DB_POOL_TIMEOUT_SECONDS,
                max_lifetime=config.DB_POOL_MAX_LIFETIME_SECONDS,
                check=ConnectionPool.check_connection, open=True,
                name=f'{component}-{database}')
        return _pools[key]


@contextmanager
def connection(component, database='agent', role='app', *, timeout=None):
    try:
        with pool(component, database, role).connection(timeout=timeout) as conn:
            yield conn
    except PoolTimeout:
        state = request_state.get()
        if state is not None:
            state['pool_timeout'] = True
        raise


def ready(component):
    # MCP needs both databases; the worker's olist reader remains lazy.
    try:
        with connection(component,timeout=config.READY_CONNECTION_TIMEOUT_SECONDS) as conn:
            conn.execute('SELECT 1')
        if component=='mcp':
            with connection(component,'olist','reader',timeout=config.READY_CONNECTION_TIMEOUT_SECONDS) as conn:
                conn.execute('SELECT 1')
        return True
    except Exception:
        return False


def close_all(component=None):
    with _lock:
        selected = [key for key in _pools if component is None or key[0] == component]
        pools = [_pools.pop(key) for key in selected]
    for item in pools:
        item.close()


atexit.register(close_all)
