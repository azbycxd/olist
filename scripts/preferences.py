"""Trusted host-side storage: all queries scope by task owner or authenticated user."""
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from config import db_kwargs


def for_task(task_id):
    with psycopg.connect(**db_kwargs("agent","app")) as conn:
        row=conn.execute("SELECT user_id FROM tasks WHERE task_id=%s",(UUID(str(task_id)),)).fetchone()
        if not row: raise ValueError("Unknown task")
        return [m for m in list_active(row[0],conn) if m['type']=='preference']


def list_active(user_id,conn=None):
    if conn is None:
        with psycopg.connect(**db_kwargs("agent","app")) as own: return list_active(user_id,own)
    rows=conn.execute("SELECT memory_id,key,value,source_quote,created_at,type,evidence,data_version FROM memories WHERE user_id=%s AND superseded_at IS NULL ORDER BY type,key",(UUID(str(user_id)),)).fetchall()
    return [{'memory_id':str(r[0]),'key':r[1],'value':r[2],'source_quote':r[3],'created_at':r[4].isoformat(),'type':r[5],'evidence':r[6],'data_version':r[7]} for r in rows]


def save(task_id,candidates,user_text,lease_token=None):
    # Validation duplicated at the trust boundary; the model process cannot write arbitrary values.
    from agent.preferences import grounded
    validated=grounded([{'key':p['key'],'source_quote':p['source_quote']} for p in candidates],user_text)
    with psycopg.connect(**db_kwargs("agent","app")) as conn:
        owner=conn.execute("SELECT user_id FROM tasks WHERE task_id=%s",(UUID(str(task_id)),)).fetchone()
        if not owner: raise ValueError("Unknown task")
        user_id=owner[0]
        conn.execute("SELECT user_id FROM users WHERE user_id=%s FOR UPDATE",(user_id,))
        if lease_token:
            from mcp_olist.leases import validate
            validate(conn,task_id,lease_token,lock=True)
        ids=[]
        for item in validated:
            old=conn.execute("SELECT memory_id,value FROM memories WHERE user_id=%s AND type='preference' AND key=%s AND superseded_at IS NULL",(user_id,item['key'])).fetchone()
            if old and old[1]==item['value']: ids.append(str(old[0])); continue
            conn.execute("UPDATE memories SET superseded_at=now() WHERE user_id=%s AND type='preference' AND key=%s AND superseded_at IS NULL",(user_id,item['key']))
            ident=conn.execute("INSERT INTO memories(user_id,type,key,value,source_quote) VALUES(%s,'preference',%s,%s,%s) RETURNING memory_id",
                (user_id,item['key'],Jsonb(item['value']),item['source_quote'])).fetchone()[0]
            ids.append(str(ident))
    return ids


def delete(user_id,memory_id):
    with psycopg.connect(**db_kwargs("agent","app")) as conn:
        return conn.execute("DELETE FROM memories WHERE user_id=%s AND memory_id=%s RETURNING memory_id",
            (UUID(str(user_id)),UUID(str(memory_id)))).fetchone() is not None
