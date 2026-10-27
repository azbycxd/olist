from db_pool import connection
"""Short transactions claim/replay transport requests; running claims have fenced owners."""
import hashlib
import json
from uuid import UUID,uuid4
import psycopg
from psycopg.types.json import Jsonb
from config import db_kwargs,SQL_TIMEOUT_SECONDS
from mcp_olist.leases import validate


def check(conn,task_id,lease_token,name,arguments):
    if name in {'run_sql','state_write'}:
        states=('running','planning') if name=='state_write' and arguments.get('role')=='planner' else ('running',)
        validate(conn,task_id,lease_token,states=states)


def begin(key,task_id,lease_token,name,arguments):
    ident=UUID(str(task_id))
    if not key.startswith(str(ident)+':') or len(key)>512: raise ValueError('Invalid task-scoped Idempotency-Key')
    digest=hashlib.sha256(json.dumps([name,arguments],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    owner=uuid4()
    with connection('mcp') as conn:
        check(conn,ident,lease_token,name,arguments)
        inserted=conn.execute("INSERT INTO tool_calls(key,task_id,request_hash,status,owner_token) VALUES(%s,%s,%s,'running',%s) ON CONFLICT DO NOTHING RETURNING key",(key,ident,digest,owner)).fetchone()
        if inserted: return owner,None
        row=conn.execute("SELECT task_id,request_hash,status,response,updated_at+%s*interval '1 second'<clock_timestamp() FROM tool_calls WHERE key=%s FOR UPDATE",(2*SQL_TIMEOUT_SECONDS,key)).fetchone()
        if row[0]!=ident or row[1]!=digest: raise ValueError('Idempotency-Key conflicts with previous request')
        if row[2]=='done': return None,row[3]
        if not row[4]: return None,{'error':'tool_in_progress','retryable':True,'notice':'正在执行，请稍后重试'}
        conn.execute('UPDATE tool_calls SET owner_token=%s,updated_at=clock_timestamp() WHERE key=%s',(owner,key))
        return owner,None


def finish(key,owner,response):
    with connection('mcp') as conn:
        updated=conn.execute("UPDATE tool_calls SET status='done',response=%s,result_id=%s,updated_at=clock_timestamp() WHERE key=%s AND owner_token=%s AND status='running' RETURNING key",(Jsonb(response),response.get('result_id'),key,owner)).fetchone()
    if not updated: return {'error':'tool_in_progress','retryable':True,'notice':'执行已由其他请求接管，请重试'}
    return response


def abandon(key,owner):
    with connection('mcp') as conn:
        conn.execute("DELETE FROM tool_calls WHERE key=%s AND owner_token=%s AND status='running'",(key,owner))


def run(key,task_id,lease_token,name,arguments,work):
    if not key: return work()
    owner,cached=begin(key,task_id,lease_token,name,arguments)
    if owner is None: return cached
    try: return finish(key,owner,work())
    except Exception:
        abandon(key,owner)
        raise
