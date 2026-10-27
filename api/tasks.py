"""Authenticated task API. Requests only enqueue; a separate process does all model work."""
from db_pool import connection
import telemetry
import asyncio
import hashlib
import hmac
import json
import os
from pathlib import Path
from uuid import UUID
from typing import Literal

import psycopg
from psycopg.types.json import Jsonb
from fastapi import Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from api.memories import app, user, issue
from agent.state import Plan, Board, Subtask
from config import FINAL_CONFIG, db_kwargs


class Credentials(BaseModel):
    model_config=ConfigDict(extra='forbid')
    username:str=Field(pattern=r'^[a-zA-Z0-9_-]{3,60}$')
    password:str=Field(min_length=10,max_length=200)


class NewTask(BaseModel):
    model_config=ConfigDict(extra='forbid')
    question:str=Field(min_length=2,max_length=6000)
    agent_mode:Literal['single','multi']='single'
    context_strategy:Literal['none','mask']='none'


def password_hash(password,salt=None):
    salt=salt or os.urandom(16).hex()
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),260000).hex()
    return 'pbkdf2_sha256$260000$'+salt+'$'+digest


def verify_password(password,stored):
    try:
        name,iterations,salt,digest=stored.split('$')
        return name=='pbkdf2_sha256' and iterations=='260000' and hmac.compare_digest(password_hash(password,salt),stored)
    except (ValueError,AttributeError):return False


def owned(conn,task_id,owner,lock=False):
    row=conn.execute('SELECT task_id,question,status,created_at,updated_at,result,error,claim_count,cancel_requested_at,deadline_at FROM tasks WHERE task_id=%s AND user_id=%s'+(' FOR UPDATE' if lock else ''),(task_id,owner)).fetchone()
    if not row:raise HTTPException(404,'Task not found')
    return dict(zip(['task_id','question','status','created_at','updated_at','result','error','claim_count','cancel_requested_at','deadline_at'],row))


def event(conn,task_id,kind,payload,tokens=0,latency_ms=0):
    # Every writer holds the task lock; seq is per-task and survives retries.
    conn.execute('SELECT task_id FROM tasks WHERE task_id=%s FOR UPDATE',(task_id,))
    seq=conn.execute('SELECT COALESCE(MAX(seq),0)+1 FROM events WHERE task_id=%s',(task_id,)).fetchone()[0]
    conn.execute('INSERT INTO events(task_id,seq,type,payload,tokens,latency_ms) VALUES(%s,%s,%s,%s,%s,%s)',
        (task_id,seq,kind,Jsonb(payload,dumps=lambda v:json.dumps(v,default=str)),tokens,latency_ms))
    return seq


@app.get('/')
def index():return FileResponse(Path(__file__).parent/'web/index.html')


@app.get('/metrics')
def metrics():
    from api.metrics import render
    from fastapi.responses import Response
    from prometheus_client import CONTENT_TYPE_LATEST
    return Response(render(),media_type=CONTENT_TYPE_LATEST)


@app.post('/register',status_code=201)
def register(body:Credentials):
    with connection('api') as conn:
        row=conn.execute('INSERT INTO users(username,password_hash) VALUES(%s,%s) ON CONFLICT(username) DO NOTHING RETURNING user_id',
            (body.username,password_hash(body.password))).fetchone()
        if not row:raise HTTPException(409,'Username unavailable')
        return {'access_token':issue(row[0]),'token_type':'bearer'}


@app.post('/login')
def login(body:Credentials):
    with connection('api') as conn:
        row=conn.execute('SELECT user_id,password_hash FROM users WHERE username=%s',(body.username,)).fetchone()
    if not row or not verify_password(body.password,row[1]):raise HTTPException(401,'Invalid credentials')
    return {'access_token':issue(row[0]),'token_type':'bearer'}


@app.post('/tasks',status_code=202)
def create_task(body:NewTask,owner:UUID=Depends(user)):
    from scripts import task_limits as limits
    settings={**FINAL_CONFIG,'AGENT_MODE':body.agent_mode,'CONTEXT_STRATEGY':body.context_strategy,
        'TOKEN_BUDGET':os.getenv('TOKEN_BUDGET','100000'),**limits.settings()}
    with telemetry.span('task.create','api'), connection('api') as conn:
        limits.owner_lock(conn,owner)
        if not limits.quota(conn,owner)['available_tokens']:raise HTTPException(429,'UTC daily token quota exhausted')
        ident=conn.execute("INSERT INTO tasks(user_id,question,background,run_config,deadline_at,traceparent) VALUES(%s,%s,true,%s,now()+%s*interval '1 second',%s) RETURNING task_id",
            (owner,body.question,Jsonb(settings),settings['TASK_MAX_SECONDS'],telemetry.traceparent())).fetchone()[0]
    return {'task_id':str(ident),'status':'pending'}


@app.get('/quota')
def get_quota(owner:UUID=Depends(user)):
    from scripts import task_limits as limits
    with connection('api') as conn:
        return {**limits.quota(conn,owner),**limits.settings()}


@app.post('/tasks/{task_id}/cancel')
def cancel(task_id:UUID,owner:UUID=Depends(user)):
    from scripts import task_limits as limits
    with connection('api') as conn:
        limits.owner_lock(conn,owner)
        task=owned(conn,task_id,owner,True)
        if task['status']=='canceled':return {'task_id':str(task_id),'status':'canceled'}
        if task['status'] in limits.TERMINAL:raise HTTPException(409,'Task already finished')
        conn.execute('UPDATE tasks SET cancel_requested_at=clock_timestamp() WHERE task_id=%s',(task_id,))
        limits.stop_task(conn,task_id,'canceled')
    return {'task_id':str(task_id),'status':'canceled'}


@app.get('/tasks')
def list_tasks(owner:UUID=Depends(user)):
    with connection('api') as conn:
        rows=conn.execute('SELECT task_id,question,status,created_at FROM tasks WHERE user_id=%s ORDER BY created_at DESC LIMIT 50',(owner,)).fetchall()
    return {'tasks':[dict(zip(['task_id','question','status','created_at'],r)) for r in rows]}


@app.get('/tasks/{task_id}')
def get_task(task_id:UUID,owner:UUID=Depends(user)):
    with connection('api') as conn:
        result=owned(conn,task_id,owner)
        result['run_config']=conn.execute('SELECT run_config FROM tasks WHERE task_id=%s',(task_id,)).fetchone()[0]
        state=conn.execute('SELECT plan,subtasks FROM task_state WHERE task_id=%s',(task_id,)).fetchone()
        from mcp_olist.embedding_config import MODEL,REVISION
        result['embedding']={'model':MODEL,'revision':REVISION}
        result['plan']=state[0] if state else None
        result['subtasks']=state[1] if state else {}
        calls=conn.execute("SELECT payload,latency_ms FROM events WHERE task_id=%s AND type='model_call' ORDER BY seq",(task_id,)).fetchall()
        recovered=conn.execute("SELECT 1 FROM events WHERE task_id=%s AND type='worker_claimed' AND payload->>'recovered'='true' LIMIT 1",(task_id,)).fetchone()
        uncertain=conn.execute("SELECT COALESCE(SUM(reserved_tokens),0) FROM model_reservations WHERE task_id=%s AND status!='settled'",(task_id,)).fetchone()[0]
        complete=all(c[0].get('usage') for c in calls) and not recovered and not uncertain
        known=sum((c[0].get('usage') or {}).get('total_tokens',0) for c in calls)
        result['usage']={'known_tokens':known,'total_tokens':known if complete else None,'usage_complete':bool(complete),
            'model_latency_ms':sum(c[1] for c in calls),'elapsed_ms':(result['updated_at']-result['created_at']).total_seconds()*1000,
            'held_tokens':uncertain,'notice':'恢复或中断请求的用量不完整，完整总量留空；预留值不是实测 token。' if recovered or uncertain else None}
        return result


@app.post('/tasks/{task_id}/confirm')
def confirm(task_id:UUID,plan:Plan,owner:UUID=Depends(user)):
    from scripts import task_limits as limits
    with connection('api') as conn:
        limits.owner_lock(conn,owner)
        limits.reap_owner(conn,owner)
    # Commit deadline expiration even when the confirmation subsequently gets 409.
    with connection('api') as conn:
        limits.owner_lock(conn,owner)
        task=owned(conn,task_id,owner,True)
        if task['status']!='awaiting_confirmation':raise HTTPException(409,'Task is not awaiting confirmation')
        stored=conn.execute('SELECT plan FROM task_state WHERE task_id=%s',(task_id,)).fetchone()
        original={p.id:p for p in Plan.model_validate(stored[0]).subtasks}
        for part in plan.subtasks:
            old=original.get(part.id)
            if part.memory_ids and (not old or part.question!=old.question or not set(part.memory_ids)<=set(old.memory_ids)):
                raise HTTPException(422,'Historical references must come from the unchanged proposed subtask')
        board=Board(plan=plan,subtasks={p.id:Subtask(question=p.question,depends_on=p.depends_on) for p in plan.subtasks})
        conn.execute('UPDATE task_state SET plan=%s,subtasks=%s,report=NULL,updated_at=now() WHERE task_id=%s',
            (Jsonb(plan.model_dump()),Jsonb({k:v.model_dump() for k,v in board.subtasks.items()}),task_id))
        conn.execute("UPDATE tasks SET status='pending',confirmed_at=now(),lease_token=NULL,lease_expires_at=NULL,updated_at=now() WHERE task_id=%s",(task_id,))
        event(conn,task_id,'plan_confirmed',{'plan':plan.model_dump()})
    return {'task_id':str(task_id),'status':'pending'}


@app.get('/tasks/{task_id}/results/{result_id}')
def result(task_id:UUID,result_id:UUID,owner:UUID=Depends(user)):
    with connection('api') as conn:
        owned(conn,task_id,owner)
        row=conn.execute('SELECT sql,columns,rows,data_version,source_result_id,truncated FROM query_results WHERE result_id=%s AND task_id=%s',(result_id,task_id)).fetchone()
        if not row:raise HTTPException(404,'Result not found')
        from mcp_olist.scopes import check_sql
        states=conn.execute('SELECT data_scope FROM users WHERE user_id=%s',(owner,)).fetchone()[0]
        if check_sql(row[0],states):raise HTTPException(403,'forbidden_dimension: 无权限')
        from mcp_olist.sql_guard import guard_sql
        return dict(zip(['sql','columns','rows','data_version','source_result_id','truncated'],(guard_sql(row[0]).sql,*row[1:])))


@app.get('/tasks/{task_id}/events')
async def events(task_id:UUID,request:Request,owner:UUID=Depends(user)):
    def authorize():
        with connection('api') as conn:owned(conn,task_id,owner)
    await asyncio.to_thread(authorize)
    try:after=max(0,int(request.headers.get('Last-Event-ID','0')))
    except ValueError:raise HTTPException(400,'Invalid Last-Event-ID')
    def poll(cursor):
        with connection('api') as conn:
            task=owned(conn,task_id,owner)
            rows=conn.execute('SELECT seq,type,payload,tokens,latency_ms FROM events WHERE task_id=%s AND seq>%s ORDER BY seq LIMIT 100',(task_id,cursor)).fetchall()
            return rows,task['status']
    async def stream():
        cursor=after
        while not await request.is_disconnected():
            rows,status=await asyncio.to_thread(poll,cursor)
            for seq,kind,payload,tokens,latency in rows:
                cursor=seq
                data=json.dumps({'type':kind,'payload':payload,'tokens':tokens,'latency_ms':latency},ensure_ascii=False,default=str)
                yield f'id: {seq}\nevent: progress\ndata: {data}\n\n'
            if status in {'completed','failed','canceled','awaiting_confirmation'} and len(rows)<100:
                yield 'event: state\ndata: '+json.dumps({'status':status})+'\n\n'
                return
            if not rows:yield ': heartbeat\n\n'
            await asyncio.sleep(.5)
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})
